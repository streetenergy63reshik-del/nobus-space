# Gate 0 — Product Contract и baseline: исследовательское досье

**Статус документа:** RESEARCH READY
**Статус реализации:** TARGET; этот документ не доказывает PASS Gate 0
**Каноническая база исследования:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
**Дата проверки источников:** 28 июля 2026 года
**Область:** Gate 0 новой дорожной карты MVP-1 Nobus Space

## 1. Назначение и границы

Этот документ сохраняет проверенные факты, рассмотренные варианты и причины
выбора средств для Gate 0. Нормативный TARGET Gate 0 находится в
[`ARCHITECTURE.md`](ARCHITECTURE.md).

Исследование не:

- переводит TARGET в CURRENT;
- подтверждает состояние живого runtime на момент чтения документа;
- разрешает изменение runtime, Scheduler, Google, Telegram или внешних данных;
- заменяет свежий Baseline Evidence Pack;
- создаёт новый eval, spec или agent framework.

## 2. Executive conclusion

Правильный Gate 0 — не ранняя реализация server/Bridge и не ещё один общий
архитектурный текст. Это воспроизводимый снимок исходного состояния и
замороженный Product Contract, по которому Gate 1–8 смогут развиваться без
расхождения терминов, контрактов, данных и критериев качества.

Принятый verdict:

- **ADAPT:** существующие contracts, policy, durable runtime, effect/evidence,
  owner-files/workspace и Google primitives;
- **ADOPT:** Pydantic, pytest, stdlib JSON/JSONL/hashlib и `pip inspect`;
- **ADOPT dev-only:** python-jsonschema, Hypothesis и Import Linter;
- **ADOPT как release checks:** pip-audit и Gitleaks;
- **PILOT LATER:** Promptfoo только как изолированный consumer канонического
  корпуса после появления проверяемого endpoint;
- **DEFER:** OpenTelemetry и Langfuse до server path и принятой retention policy;
- **REJECT FOR GATE 0:** DeepEval, hosted evals с рабочим корпусом, новый
  eval/spec/agent framework и собственная observability platform.

## 3. Проверенный канонический контекст

### 3.1. Нормативные источники

Исследование сверено с exact Git blobs commit `9d816b35...`:

- `docs/README.md`;
- `docs/12-Эталон-MVP-1-и-дорожная-карта.md`;
- `docs/adr/0017-hybrid-natural-google-local-document-plane.md`;
- `docs/handoffs/CURRENT-STATUS.md`;
- `docs/handoffs/MVP-1-ISSUES.md`;
- `docs/handoffs/WORKSPACE-INVENTORY.md`;
- `docs/05-Спецификации-контрактов.md`;
- `docs/06-Регламент-качества-L1-L4.md`.

Иерархия источников требует различать:

- принятый ADR и канонический TARGET;
- проверяемый CURRENT;
- runtime evidence;
- исторические handoff и research.

Документ или ADR не становится доказательством работающего runtime.

### 3.2. Verified CURRENT

По `CURRENT-STATUS.md` и read-only инвентаризации кода текущий owner-bound
локальный продукт уже имеет:

- Telegram owner binding, один polling contour, durable SQLite queue/outbox и
  restart recovery;
- text/voice ingress и persistent Codex SDK;
- read-only web research с evidence;
- Google Calendar, Tasks и Drive primitives;
- bounded local owner-file read и owner artifact delivery;
- durable product effects, approval binding, idempotency и reconciliation;
- backup/restore и SQLite integrity primitives;
- L1/L2/L3 evidence model.

Это локальный owner-bound runtime, а не готовый server/Bridge или коммерческий
multi-tenant SaaS.

### 3.3. Verified TARGET

Следующие элементы остаются TARGET:

- Server Nobus Core + Google Workspace + Windows Local Library Bridge;
- единый lifecycle
  `search → select → read → analyze → create/update → deliver`;
- production `IntentEnvelope`, `DocumentRef`, `DocumentQuery`,
  `DocumentReadPlan`, `AnalysisRequest`, `ArtifactPlan` и
  `DocumentWritePlan`;
- Google Docs/Sheets writeback;
- authenticated Bridge;
- server-grade tenant identities;
- новый Gate 0–8 handoff и hybrid release.

Статический поиск в `src/` и `tests/` на base commit не обнаружил реализаций
семи новых hybrid contracts.

## 4. Baseline-разрыв: docs, repo и runtime

Исследование подтвердило:

- documentation worktree HEAD:
  `9d816b35d3f419b42e24ad09ae6aadc92c33db43`;
- `CURRENT-STATUS.md` называет runtime/live commit `b69e846`;
- `b69e84687cdce439c42f1bc53e4fe7654e4deaf9` является предком
  локального live worktree commit
  `1ac52a00fd22b25cb6fcbd9f694688157c900cc8`;
- documentation commit `9d816...` не является предком `1ac52a...`.

Это не доказывает дефект runtime. Это доказывает, что существуют разные
evidence layers:

1. canonical documentation commit;
2. development repository commit;
3. live runtime worktree commit;
4. фактически загруженный process/runtime state;
5. DB/config/registry state.

Gate 0 обязан фиксировать их раздельно. Поле `repo_commit` не может подменять
`runtime_commit`, а наличие commit в worktree не доказывает, что именно он
загружен процессом.

`WORKSPACE-INVENTORY.md` актуален на 24 июля 2026 года и является полезным
операционным источником, но не свежим снимком worktree/runtime на 28 июля.

## 5. Карта существующего кода и reuse

| Блок | Проверенная возможность | Verdict |
|---|---|---|
| `src/contracts/models.py` | `ContractModel`, canonical JSON digest, trusted ingress, task, worker, verification и approval contracts | ADAPT как единый contract source |
| `src/core/policy.py` | trusted verifier registry, transition/completion/approval guards | ADAPT |
| `src/application/durable_runtime.py` | durable execution, attempt/retry/recovery | REUSE |
| `src/application/product_effects.py` | closed effects, digest/idempotency, approval/receipt binding | ADAPT |
| `src/application/owner_files.py` | bounded read, file identity, containment и sensitive-text guards | REUSE |
| `src/application/owner_workspace.py` | proposal, snapshot, CAS, atomic update, readback, reparse protection | REUSE |
| `src/application/runtime_maintenance.py` | SQLite `quick_check`, backup/restore validation, dead-letter inspection | REUSE в baseline |
| `src/integrations/google_calendar.py` | Calendar primitive | ADAPT |
| `src/integrations/google_tasks.py` | exact list resolution, idempotency marker, safe mutation behavior | ADAPT |
| `src/integrations/google_drive.py` | bounded metadata/content plane и scope validation | ADAPT |
| `src/integrations/google_transport.py` | safe-read retry и mutation retry boundary | REUSE |
| `src/storage/sqlite_store.py` | durable task/evidence state | REUSE |
| `src/storage/outbox.py` | durable delivery records | REUSE |
| `src/orchestrator/intent_parser.py` | существующий CURRENT parser | BASELINE ONLY; не новый `IntentEnvelope` |
| `scripts/backup_telegram_runtime.py` | authenticated backup manifest pattern | ADAPT для evidence manifest ideas |
| `scripts/check_telegram_health.py` | read-only runtime health primitives | ADAPT |
| `ops/windows/Install-NobusSpaceBot.ps1` | Scheduler/runtime installation knowledge | READ-ONLY evidence source |

На base commit найдено 83 test-файла и 880 явных test functions до
parametrized expansion. Существующие regression suites следует переиспользовать,
а не переносить в новый test runner.

## 6. Исследованный landscape

### 6.1. Contract и schema tools

#### Pydantic 2.13.4 — ADOPT

- Уже зафиксирован в `requirements.txt`.
- Генерирует JSON Schema Draft 2020-12 через `model_json_schema()`.
- Поддерживает closed validation, strict mode и `extra="forbid"`.
- MIT, Python/Windows/VPS, без внешней передачи данных.
- Удаляет необходимость собственной validation/serialization layer.

Источники:

- [Pydantic JSON Schema](https://pydantic.dev/docs/validation/latest/concepts/json_schema/)
- [Pydantic configuration](https://pydantic.dev/docs/validation/latest/api/pydantic/config/)
- [Pydantic releases](https://github.com/pydantic/pydantic/releases)
- [Pydantic license](https://github.com/pydantic/pydantic/blob/main/LICENSE)

#### python-jsonschema 4.26.0 — ADOPT dev-only

- Независимая реализация JSON Schema для L2-проверки Pydantic output.
- Поддерживает Draft 2020-12.
- MIT, Python, локальное выполнение.
- Не становится production runtime dependency.

Источники:

- [python-jsonschema repository](https://github.com/python-jsonschema/jsonschema)
- [JSON Schema specification tests](https://github.com/json-schema-org/JSON-Schema-Test-Suite)

#### Hypothesis 6.161.7, 27 июля 2026 — ADOPT dev-only

- Property-based testing и shrinking.
- Подходит для Unicode, normalization, recursive payload, size/depth, replay,
  idempotency и hostile path cases.
- MPL-2.0, Python/Windows.
- Минимальный failing example должен сохраняться как deterministic regression.

Источники:

- [Hypothesis releases](https://github.com/HypothesisWorks/hypothesis/releases)
- [Hypothesis license](https://github.com/HypothesisWorks/hypothesis/blob/master/LICENSE.txt)

### 6.2. Golden corpora и eval

#### pytest 9.1.1 + JSONL — ADOPT

- Уже зафиксирован в проекте.
- Канонический corpus остаётся обычным versioned JSONL.
- Детерминированные expected intent/effect/error решения выражаются pytest
  assertions.
- Нет второго DSL, runtime или database.

#### Promptfoo 0.121.6 — PILOT LATER

Полезные возможности:

- prompt regression;
- model/provider comparison;
- assertions, red-team и HTTP adapters;
- JSON/JSONL/JUnit/HTML exports;
- локальный CLI и MCP server.

Ограничения:

- отдельный Node runtime: Node `^20.20.0` или `>=22.22.0`, после завершения
  поддержки Node 20 рекомендован Node 24;
- default telemetry и update checks;
- local SQLite/cache/UI создают второй state contour;
- basic self-host не имеет встроенной auth/SSO и не является production
  multi-team platform;
- configuration допускает JavaScript callbacks; открыта просьба о safe mode;
- нельзя передавать ему credentials через config/UI/export.

Источники:

- [Promptfoo installation and Node support](https://www.promptfoo.dev/docs/installation/)
- [Promptfoo self-hosting](https://www.promptfoo.dev/docs/usage/self-hosting/)
- [Promptfoo telemetry](https://www.promptfoo.dev/docs/configuration/telemetry/)
- [Promptfoo outputs](https://www.promptfoo.dev/docs/configuration/outputs/)
- [Promptfoo security policy](https://github.com/promptfoo/promptfoo/security)
- [Safe mode issue #10018](https://github.com/promptfoo/promptfoo/issues/10018)
- [Supply-chain hardening issue #9985](https://github.com/promptfoo/promptfoo/issues/9985)
- [Promptfoo releases](https://github.com/promptfoo/promptfoo/releases)
- [Promptfoo license/readme](https://github.com/promptfoo/promptfoo/blob/main/README.md)

Условия будущего pilot:

- canonical corpus и expected decisions остаются в Nobus JSONL/pytest;
- Promptfoo получает обезличенный export или вызывает bounded Nobus endpoint;
- exact version pin;
- telemetry и update checks отключены;
- только trusted configuration;
- localhost или изолированный CI job;
- raw owner/client payload и credentials запрещены;
- полезность должна быть измерена удалённым custom eval code или найденными
  регрессиями.

#### DeepEval 4.0.5 — REJECT FOR GATE 0

- Apache-2.0, Python и pytest-style API.
- Имеет LLM metrics и dataset integrations.
- Дублирует canonical pytest/corpus contour.
- Многие метрики требуют model judge, создают cost/provider/data dependence.
- Базовая PostHog telemetry включена по умолчанию, хотя может быть отключена.

Источники:

- [DeepEval repository](https://github.com/confident-ai/deepeval)
- [DeepEval releases](https://github.com/confident-ai/deepeval/releases)
- [DeepEval data privacy](https://deepeval.com/docs/data-privacy)

#### OpenAI/Google hosted evals — LEARN, DEFER UPLOAD

Полезны для открытых quality dimensions и model-judge experiments, но не должны
решать закрытые tenant/security/effect assertions. Рабочий Nobus corpus нельзя
загружать без отдельной data/retention/cost policy.

Источники:

- [OpenAI Evals API](https://platform.openai.com/docs/api-reference/evals)
- [OpenAI endpoint data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)
- [OpenAI Evals repository](https://github.com/openai/evals)
- [Vertex Gen AI Evaluation SDK](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/eval-python-sdk/view-evaluation)
- [Vertex judge model calibration](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/evaluate-judge-model)

### 6.3. Architecture fitness

#### Import Linter 2.11, 6 марта 2026 — ADOPT dev-only

- Проверяет layers, independence и forbidden imports.
- BSD-2, Python, low operational load.
- Предпочтительнее самописного AST scanner.
- Gate 0 должен определить только 4–6 критических rules.

Источники:

- [Import Linter contract types](https://import-linter.readthedocs.io/en/v2.3/contract_types.html)
- [Import Linter release notes](https://import-linter.readthedocs.io/en/stable/release_notes/)
- [Import Linter repository](https://github.com/seddonym/import-linter)

`pytestarch`, ArchUnit-подобные layers и ADR tooling не выбраны: у проекта уже
есть pytest, собственный ADR format и достаточная layered structure.

### 6.4. Inventory, supply chain и release

#### `pip inspect` — ADOPT

- Встроенный stable JSON inventory format pip.
- Не требует новой зависимости или сети.
- Подходит для Windows и VPS.
- Фиксирует фактически установленные distributions и environment metadata.

Источник:

- [pip inspect JSON report specification](https://pip.pypa.io/en/stable/reference/inspect-report/)

#### pip-audit 2.10.0 — ADOPT release check

- PyPI/OSV vulnerability report и CycloneDX output.
- Apache-2.0, Python >= 3.10.
- Требует сети для актуальной проверки.
- Не доказывает отсутствие malicious package и не должен auto-fix release.

Источники:

- [pip-audit repository](https://github.com/pypa/pip-audit)
- [pip-audit releases](https://github.com/pypa/pip-audit/releases)

#### Gitleaks 8.28.x — ADOPT release check

- Local secret scanning для Windows/Linux.
- MIT, готовый binary.
- Заменяет собственный secret scanner.
- False positives оформляются точечными allowlists с review, не общим
  отключением.

Источники:

- [Gitleaks repository](https://github.com/gitleaks/gitleaks)
- [Gitleaks releases](https://github.com/gitleaks/gitleaks/releases)
- [Gitleaks license](https://github.com/gitleaks/gitleaks/blob/master/LICENSE)

Semgrep оставлен до появления конкретной threat model и набора правил.

### 6.5. Observability

#### OpenTelemetry Python 1.42.1 — DEFER SDK

- Backend-neutral traces/metrics.
- Apache-2.0, Python 3.10+.
- Traces и metrics stable; logs остаются development.
- GenAI semantic conventions развиваются и могут раскрывать tool
  arguments/results, если включить их без field policy.

Gate 0 должен заморозить sanitized internal event vocabulary, но не добавлять
exporter/backend.

Источники:

- [OpenTelemetry Python status](https://opentelemetry.io/docs/languages/python/)
- [OpenTelemetry Python releases](https://github.com/open-telemetry/opentelemetry-python)
- [Semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [GenAI attributes](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)

#### Langfuse v3 self-host / Cloud v4 — DEFER

- LLM traces, datasets, feedback и eval UI.
- Core MIT; enterprise functions имеют отдельные условия.
- Self-host требует PostgreSQL, ClickHouse, Redis и object storage.
- Retention self-host по умолчанию требует управления владельцем; часть
  автоматизации retention относится к коммерческим функциям.
- Cloud/self-host major-version compatibility находится в переходе v3/v4.

Источники:

- [Langfuse compatibility](https://langfuse.com/docs/compatibility)
- [Langfuse self-hosting](https://langfuse.com/self-hosting)
- [Langfuse encryption](https://langfuse.com/self-hosting/configuration/encryption)
- [Langfuse data retention](https://langfuse.com/docs/administration/data-retention)
- [Langfuse data isolation](https://langfuse.com/security/data-isolation)
- [Langfuse license](https://github.com/langfuse/langfuse/blob/main/LICENSE)
- [Langfuse releases](https://github.com/langfuse/langfuse/releases)

## 7. Shortlist

| Вариант | Состав | Собственный код | Ops/lock-in | Verdict |
|---|---|---:|---|---|
| Native minimal | Pydantic + pytest + stdlib + `pip inspect` | Низкий | Минимальные | Valid fallback |
| **Balanced** | Native + jsonschema + Hypothesis + Import Linter; внешние pip-audit/Gitleaks | **Минимальный при независимой проверке** | Низкие; dev-only | **Recommended** |
| Platform-heavy | Promptfoo + DeepEval + OTel + Langfuse | Меньше UI-кода, но больше adapters/config | Высокие, Node/cloud/state | Reject for Gate 0 |

## 8. Buy / adopt / adapt / build

### BUY

Платный сервис для Gate 0 не требуется.

### ADOPT

- Pydantic;
- pytest;
- stdlib JSON/JSONL/hashlib;
- `pip inspect`;
- dev-only jsonschema, Hypothesis, Import Linter;
- pip-audit и Gitleaks как release tools.

### ADAPT

- canonical digest и closed models;
- policy/verifier registry;
- durable state/effects/outbox;
- evidence records;
- owner file/workspace safety;
- Google Calendar/Tasks/Drive primitives;
- runtime maintenance и manifest patterns.

### BUILD

Только Nobus-specific:

- Product Contract;
- Baseline Evidence Pack;
- corpus taxonomy и обезличенный corpus;
- expected intent/effect/error fixtures;
- registry/evidence schemas;
- несколько architecture fitness contracts;
- Gate handoff.

### DO NOT BUILD

- собственный JSON Schema validator;
- собственный test runner;
- собственный eval UI;
- собственный tracing backend;
- второй contract/digest framework;
- общий plugin/agent framework «на будущее».

## 9. Ключевые root causes и риски

| Root cause | Риск | Архитектурная мера |
|---|---|---|
| Старый локальный и новый hybrid Gate 0 имеют одно имя | Ложное наследование PASS | Новый lineage-bound handoff |
| Документ принимается за runtime evidence | TARGET объявляется CURRENT | Раздельные evidence layers и freshness |
| Параллельные модели/digest | Несовместимые Telegram/Core/Bridge payloads | Один Pydantic source |
| LLM grader раньше deterministic oracle | Вариативная security acceptance | Closed assertions только pytest/schema |
| Eval/trace data authority не определена | Утечка owner/client content | Local sanitized corpus, exporter off |
| Node/Python tool sprawl | Две CI/runtime цепочки | Promptfoo только consumer |
| Windows/server semantics расходятся | Ошибки path/Bridge boundary | Platform matrix и hostile path corpus |
| Local configured identities принимаются за service auth | Ложная tenant security | Явное CURRENT limitation |
| Evidence не имеет срока | Stale PASS | Timestamps, TTL и invalidation |
| Unknown write outcome повторяется | Duplicate effect | Reconciliation, no blind retry |
| Непинованные tools/actions | Supply-chain drift | Exact pins, hashes и audit |

## 10. Исследовательские критерии рекомендации

Balanced stack выбран не по stars, а потому что:

1. переиспользует уже установленный Pydantic/pytest;
2. не добавляет production dependency;
3. работает локально на Windows и Python VPS;
4. не требует передачи corpus в облако;
5. даёт независимую schema/property/architecture проверку;
6. оставляет JSONL и JSON Schema переносимыми;
7. позволяет удалить ручные validators и большие списки boundary examples;
8. имеет простой fallback к native-only contour;
9. не мешает позже подключить Promptfoo или OTel как consumer.

## 11. Вопросы владельцу, не блокирующие design

До соответствующих следующих Gate потребуются решения:

1. Может ли raw owner/client content покидать Nobus server для eval или
   observability? Рекомендация: нет.
2. Каков срок хранения sanitized operational events? Рекомендация по умолчанию:
   30 дней; raw prompts/documents не хранить в trace backend.
3. Каков допустимый budget model-graded evals в Gate 3/6? Рекомендация:
   нулевой для Gate 0, отдельный capped budget позже.
4. Как оформлять offline Bridge и unknown write outcome? Рекомендация:
   bounded wait → `DEGRADED`; write только после reconciliation или нового
   approval.

## 12. Проверка исследования

### L1

- exact base commit и обязательные Git blobs подтверждены;
- code/test inventory выполнен read-only;
- ссылки на первичные источники сохранены;
- семь новых contracts и новый eval stack не выданы за CURRENT.

### L2

- conclusions сверены с canonical docs, CURRENT code и requirements;
- версии, лицензии, maintenance, privacy и security проверены по официальным
  documentation/repositories/releases/issues;
- shortlist сравнивает три реалистичных эксплуатационных варианта.

### L3

Проверены способы получить ложный результат:

- смешать docs, repo и live runtime commits;
- загрузить рабочий corpus/traces в облако;
- сделать Promptfoo source of truth;
- позволить model judge решать tenant/effect safety;
- добавить новый framework без потребителя;
- объявить Gate 0 PASS до свежего evidence.

**Итог:** `RESEARCH READY`. PASS Gate 0 может быть установлен только после
реализации [`ARCHITECTURE.md`](ARCHITECTURE.md), свежего Baseline Evidence Pack
и независимого Gate handoff.
