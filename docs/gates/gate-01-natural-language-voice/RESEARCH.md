# Gate 1 — Natural Language + Voice Kernel: исследовательское досье

**Статус документа:** RESEARCH READY
**Статус реализации:** TARGET; документ не доказывает PASS Gate 1
**Каноническая база:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
**Дата проверки источников:** 28 июля 2026 года
**Область:** Gate 1 дорожной карты MVP-1 Nobus Space

## 1. Executive conclusion

Gate 1 не нуждается в agent framework. Ему нужен один строгий смысловой контракт
и небольшая детерминированная машина состояний между trusted ingress и уже
существующими application adapters.

Нормативный verdict:

- **ADOPT:** Pydantic `2.13.4`, уже закреплённый в проекте, как единственный
  runtime validator и источник JSON Schema для `IntentEnvelope`;
- **ADAPT:** native strict Structured Outputs выбранного model provider только
  для `SemanticProposal`; tools/function execution в этом вызове запрещены;
- **BUILD SMALL:** provider-neutral gateway, один `IntentEnvelope`, scoped
  conversation state machine, exact one-question clarification и safe error
  taxonomy;
- **REUSE:** trusted ingress, durable queue, outbox, idempotency, adapter
  contracts, product effects, reconciliation и L1–L3;
- **REUSE/ADAPT VOICE:** local-first `faster-whisper==1.2.1`; cloud ASR —
  только optional fallback после Gate 3 privacy/policy/cost acceptance;
- **REJECT AS GATE 1 RUNTIME:** OpenAI Agents SDK, Google ADK, PydanticAI и
  LangGraph. Их полезные идеи не компенсируют второй lifecycle/state/tool
  contour и лишнюю authority surface;
- **FALLBACK:** slash-команды и узкие детерминированные parsers остаются
  совместимым fail-safe путём, но обязаны создавать тот же `IntentEnvelope`.

Максимально важная граница: модель предлагает смысл, но не выбирает исполняемый
tool, credential, tenant, adapter, permission, risk или effect authority. Core
детерминированно разрешает source/target, выбирает adapter, заново выводит effect
и применяет policy/idempotency/evidence.

## 2. Scope, метод и уровни доказательств

Исследование выполнено read-only по:

- канонической документации и ADR на exact commit;
- релевантным `src/` и `tests/`;
- официальным документациям provider;
- первичным repositories, releases и package registries.

Обозначения доказательств:

- **L1:** локальный канон, исходный код, schema/package metadata;
- **L2:** официальная спецификация provider либо независимое воспроизведение;
- **L3:** security advisory, adversarial test/benchmark либо вывод, проверяемый
  через явную threat model.

Цена и retention зависят от региона, endpoint, договора и даты. Поэтому они не
зашиваются в архитектуру: Gate 3 обязан принять versioned provider policy и
budget. Никакие model/ASR live calls в этом исследовании не выполнялись.

## 3. Source of truth и CURRENT/TARGET

### 3.1. Канонические локальные источники

- [`../../README.md`](../../README.md);
- [`../../12-Эталон-MVP-1-и-дорожная-карта.md`](../../12-Эталон-MVP-1-и-дорожная-карта.md);
- [`../../02-Глоссарий.md`](../../02-Глоссарий.md);
- [`../../05-Спецификации-контрактов.md`](../../05-Спецификации-контрактов.md);
- [`../../adr/0012-owner-command-authority-and-calendar.md`](../../adr/0012-owner-command-authority-and-calendar.md);
- [`../../adr/0014-natural-product-router-and-bounded-context.md`](../../adr/0014-natural-product-router-and-bounded-context.md);
- [`../../adr/0017-hybrid-natural-google-local-document-plane.md`](../../adr/0017-hybrid-natural-google-local-document-plane.md);
- [`../../handoffs/CURRENT-STATUS.md`](../../handoffs/CURRENT-STATUS.md);
- [`../../handoffs/MVP-1-ISSUES.md`](../../handoffs/MVP-1-ISSUES.md).

Nobus Memory не использовалась как источник CURRENT/TARGET. Исторический индекс
не может заменить exact blob, код или воспроизводимый runtime evidence.

### 3.2. Проверенный CURRENT

В owner-bound Telegram runtime уже есть:

- authenticated `TrustedIngressEnvelope`, update idempotency и tenant binding;
- text и voice transport;
- локальный `faster-whisper`, bounded audio, temp cleanup и startup warmup;
- durable queue/restart recovery, outbox и result delivery;
- отдельные Calendar, Google Tasks, Drive, owner-file, document, Notes, Memory
  и research routes;
- закрытые domain actions и application-owned effects;
- delete/action-bound approval, effect receipts и reconciliation;
- 10-минутный follow-up Google Tasks внутри exact
  `(tenant, chat, message_thread_id)`;
- safe сообщения для части domain failures.

Однако natural routing реализован каскадом hints/regex в
`src/application/telegram_product.py:1134-1425`, а не единым production
`IntentEnvelope`. Отдельный `src/orchestrator/intent_parser.py` распознаёт
старые `audit/report/status/help` и возвращает mutable `payload` без Core
authority invariants. `src/orchestrator/router.py` содержит ещё одну карту
intent → agent. Это разные модели смысла.

Voice сейчас проходит `download → faster-whisper → transcript string →
_start_owner_instruction` (`telegram_product.py:1523-1548`). Поле
`TranscriptResult.confidence` фактически получает `language_probability`, то
есть вероятность языка, а не калиброванную уверенность в словах/команде.

### 3.3. TARGET

TARGET из документа 12 и ADR 0017:

```text
Telegram text/voice
  → trusted ingress
  → local voice transcription (voice only)
  → one IntentEnvelope
  → deterministic policy/source/adapter selection
  → durable queue/worker
  → application-owned effect
  → verified result/outbox
```

Обычный русский текст и подтверждённая транскрипция становятся основным
интерфейсом. Slash остаётся fallback. Неоднозначность приводит ровно к одному
понятному вопросу, а не к угадыванию и не к generic failure.

## 4. End-to-end failure map и root causes

| Этап | CURRENT механизм | Наблюдаемый класс отказа | Системная причина | TARGET control |
|---|---|---|---|---|
| Telegram ingress | strict gateway | malformed/replay в основном закрыты | transport уже силён; проблема ниже | без изменения authority |
| Voice download | 10 MiB product cap, Telegram `getFile` | oversize/network/format схлопываются | одна broad exception ветка | typed voice errors |
| ASR | faster-whisper `base/int8` | термин/число/имя может исказиться | language probability ошибочно выглядит confidence | calibrated ASR quality + confirmation state |
| Domain choice | ordered regex/hints | неверная тема или раннее перехватывание | порядок `if` является скрытой политикой | один schema-constrained proposal |
| Planner choice | domain-specific planners | provider error выглядит domain failure | семантика и transport/planner смешаны | provider-neutral outcome taxonomy |
| Follow-up | отдельный Tasks dict | чужая тема/устаревший контекст | state только для одного домена и process-memory | durable scoped frame + revision/TTL |
| Clarification | ad hoc text | несколько вопросов или общий совет | нет формального ambiguity contract | одна `Clarification` на frame |
| Tool/adapter | выбран веткой router | model/planner shape связан с adapter | несколько параллельных action schemas | Core route registry |
| Effect | application effects | сильные проверки уже есть | intent ещё не является единым входом | повторный derivation/effect gate |
| Worker | generic SDK route | plain/minimal/planner JSON mismatch | answer protocol использовался как routing fallback | semantic gateway отделён от answer worker |
| Result | broad exception | «не удалось обработать» | exception type теряется между слоями | safe stable error code + owner message |
| Retry/outage | локальные retries | silent semantic drift при fallback | fallback не является contract decision | no silent cross-provider fallback |

Основные root causes:

1. **Смысл размазан по порядку кода.** Regex, domain planners, profile prefixes
   и worker fallback конкурируют за один запрос.
2. **Нет единой границы proposal/authority.** Domain action schemas закрыты, но
   до них не существует одного закрытого intent contract.
3. **Conversation state фрагментарен.** Scope для Tasks правильный, но не
   обобщён и не durable.
4. **Confidence некалиброван.** Model self-score и language probability не
   равны вероятности корректного effect.
5. **Ошибки теряют provenance.** ASR, provider, validation, target resolution,
   policy и adapter failure часто попадают в одну owner-facing ветку.
6. **Миграционные слои накопились.** Старый `IntentParser/TaskRouter`, natural
   product hints и domain planners задают три разных routing vocabulary.

## 5. Исследованные архитектурные варианты

### Вариант A — расширять CURRENT regex/planner cascade

Состав: добавлять hints, negative guards и domain contexts в
`telegram_product.py`.

Плюсы:

- минимальный первоначальный diff;
- низкая latency для известных формулировок;
- offline и детерминированность на fast paths.

Минусы:

- комбинаторный рост порядка/исключений;
- новая функция требует «магической формулировки»;
- невозможно единообразно выразить ambiguities, confidence и effects;
- follow-up остаётся domain-specific;
- L2 corpus проверяет реализацию, но не стабильный contract.

**Verdict: REJECT как TARGET; оставить временным fallback/migration oracle.**

### Вариант B — framework-led agent runtime

Состав: Agents SDK/ADK/PydanticAI/LangGraph владеет routing, state, tools и
handoffs.

Плюсы:

- готовые abstractions для tool calls, graph, sessions, traces и HITL;
- быстрые demos;
- provider integrations.

Минусы для Nobus:

- дублирует durable queue/state/outbox/reconciliation;
- создаёт второй tool/permission contour;
- сложнее доказать, что model handoff не расширил authority;
- schema/session upgrades становятся migration surface;
- framework tracing может сохранять sensitive input/output;
- текущие adapters и effect gates всё равно нельзя удалить.

**Verdict: REJECT как Gate 1 runtime.** Отдельные test/eval ideas допустимы
позже, но не production dependency.

### Вариант C — strict proposal + deterministic Core state machine

Состав:

- Pydantic contract;
- native Structured Outputs без tools;
- provider-neutral adapter;
- маленькая state machine;
- route/effect registry в Core;
- существующий durable runtime.

Плюсы:

- одна схема и один audit point;
- vendor-neutral semantics;
- минимальный новый state;
- ясный outage/fallback;
- reuse сильных Nobus primitives;
- frameworks можно удалить из Gate 1 path.

Минусы:

- собственные schema validators и state transitions надо тщательно тестировать;
- provider-specific schema subset требует compile/check;
- нужна golden corpus calibration.

**Verdict: RECOMMENDED, BUILD SMALL.**

## 6. Structured intent routing landscape

### 6.1. Native Structured Outputs — ADOPT/ADAPT

OpenAI Structured Outputs гарантирует соответствие поддерживаемому JSON Schema,
даёт программно различимый refusal, но отдельно документирует incomplete output
и поддерживает не весь JSON Schema. Поэтому transport success не равен принятому
intent: Nobus всё равно выполняет Pydantic validation и semantic validators.

Gemini Structured Outputs также принимает JSON Schema/Pydantic и прямо
показывает локальную `model_validate_json`. Это подтверждает переносимость
подхода «provider proposal → local validation».

Функциональный вызов обоих provider не нужен. Function calling предназначен для
выбора/аргументов функций и создаёт лишний путь к tool execution. Gate 1
передаёт `tools=[]` и принимает только text structured output.

### 6.2. OpenAI Agents SDK `0.19.0`, 27 июля 2026 — REJECT RUNTIME

- MIT, Python, активно поддерживается;
- useful: typed output, sessions, handoffs, guardrails, tracing;
- mismatch: агентный lifecycle и tools не нужны для одного semantic proposal;
- tracing — отдельная privacy/retention поверхность;
- добавляет abstraction над уже существующими Core/queue/outbox.

Использование SDK не удаляет ни policy, ни idempotency, ни adapters. Значит,
чистого выигрыша Gate 1 нет.

### 6.3. Google ADK `2.5.0`, 16 июля 2026 — REJECT RUNTIME

- Apache-2.0, Python ≥3.10, активная разработка;
- ADK 2.0 принёс breaking changes в agent API, event model и session schema;
- workflow runtime, delegation, fan-out/loops избыточны;
- создаёт lock-in к ADK session/event lifecycle поверх Nobus lifecycle.

### 6.4. PydanticAI `2.19.0`, 28 июля 2026 — REJECT RUNTIME

- MIT, Python ≥3.10, production/stable classifier;
- хорошая provider abstraction, typed outputs, durable integrations и evals;
- быстро меняющаяся release line;
- дублирует тонкий gateway, который для Nobus состоит из одного bounded call;
- agent/tool abstractions расширяют test surface без удаления existing code.

Pydantic как validation library принимается; PydanticAI как runtime — нет.

### 6.5. LangGraph `1.2.9`, 10 июля 2026 — REJECT FOR GATE 1 PATH

- MIT, Python ≥3.10, зрелые persistence/interrupt primitives;
- уже закреплён в `requirements.txt` и используется старым
  `src/orchestrator/graph.py`;
- Gate 1 state machine имеет около десяти состояний и не требует graph runtime;
- checkpoint semantics дублируют Nobus durable storage.

Удаление dependency не является задачей Gate 1 architecture. После миграции
нужен repo-wide consumer check; нормативно LangGraph не должен быть импортирован
новым intent kernel.

### 6.6. Minimal state machine — BUILD

Обычный closed enum state + transition table + optimistic revision/CAS:

- проще формально проверить;
- события сериализуются существующим storage pattern;
- unknown transition fail-closed;
- нет model-controlled graph edge;
- rollback — feature flag, а не state migration framework.

## 7. Voice landscape

| Кандидат | RU/качество | Windows/VPS/latency | Privacy/offline | Ops/lock-in | Verdict |
|---|---|---|---|---|---|
| `faster-whisper 1.2.1` | Whisper multilingual, beam/VAD/hotwords; нужен собственный RU corpus | Python/CTranslate2, CPU int8/GPU; уже интегрирован | полностью local после model cache | низкий; MIT | **Primary** |
| OpenAI Whisper `v20250625` | reference implementation, large-v3/turbo | PyTorch тяжелее на Windows CPU | local/offline | средний; MIT | benchmark/reference |
| `whisper.cpp 1.9.1` | те же model families, quantization | сильный native Windows/CPU fallback | local/offline | отдельный binary/model packaging; MIT | optional operational fallback |
| Google Cloud STT V2 | `ru-RU`, Chirp/Chirp 2/3 и word confidence по model/region | network latency; managed scale | cloud; logging default off, но policy/region нужны | cost/provider lock-in | Gate 3 optional fallback |
| Gemini audio understanding | гибкая semantic работа с audio | не специализированный deterministic STT contract | cloud/data policy | model/cost lock-in | reject as primary ASR |

Рекомендованный voice path:

1. Telegram validates metadata, duration ≤300 s и product byte cap ≤10 MiB
   (строже официального download max 20 MiB).
2. Audio обрабатывается в bounded local temp root.
3. faster-whisper получает `language="ru"` и принятые ADR 0012 settings.
4. Quality вычисляется из calibrated features; `language_probability` не
   называется transcript confidence.
5. Неуверенная транскрипция переходит в `awaiting_transcript_confirmation`.
6. Audio удаляется после безопасной обработки; сохраняются digest и bounded
   metadata, не raw audio.
7. Cloud ASR отключён до Gate 3. При разрешении он не включается silent fallback:
   нужен policy flag, classification check, owner-visible degraded mode и audit.

Диаrization не входит в Gate 1: Telegram voice note в owner control plane имеет
одного ожидаемого говорящего, а diarization увеличивает latency/dependency и не
решает intent correctness.

## 8. Security, privacy и confidence

### Prompt injection

Prompt-only защита недостаточна. OpenAI прямо рекомендует ограничивать impact,
даже если manipulation succeeds. В Nobus это означает:

- model call не имеет tools;
- trusted fields никогда не читаются из owner text;
- retrieved web/document/history помечаются untrusted data;
- source registry и route registry application-owned;
- effect выводится Core повторно;
- consequential sink закрывается policy/L4.

### Scoped context и poisoning

Provider не получает «всю беседу». Вход semantic proposal:

- текущий owner text;
- один active frame того же tenant/actor/chat/topic;
- bounded sanitized summary выбранных слотов;
- не более одного предыдущего verified result, только если он нужен follow-up.

Untrusted file/web content никогда не становится conversation instruction.
Смена домена, истёкший TTL или новый complete intent закрывает старый frame.

### Confidence calibration

Model self-confidence — feature, не authority. Итоговый `confidence`:

- хранится как integer basis points `0..10000`, без float drift;
- калибруется на held-out Russian corpus;
- используется для clarification/telemetry;
- не снижает policy requirement и не разрешает effect;
- acceptance оценивает reliability diagram/Brier/ECE, а не только среднее.

ASR quality и semantic confidence раздельны. Низкое значение любого из них
может вызвать один вопрос, но два независимых вопроса не показываются
одновременно: state machine выбирает самый ранний blocking ambiguity.

### Retention

Local-first исключает передачу audio cloud provider. Для semantic API остаются
минимизированный owner text и scoped metadata. OpenAI официально указывает
30-дневный abuse-monitoring retention для Responses/Chat Completions по default,
а ZDR требует eligibility/approval; `store=false` обязателен, но сам по себе не
равен ZDR. Эти условия принимает Gate 3. Secrets, raw audio, absolute local paths
и unrelated history в provider request запрещены.

## 9. Shortlist и adopt/adapt/build/reject

| Решение | Зрелость | Windows/VPS | Privacy/cost | Код, который можно убрать | Lock-in | Verdict |
|---|---|---|---|---|---|---|
| Native SO + Pydantic + small FSM | высокий primitives / собственная интеграция | да/да | один bounded semantic call | regex cascade, duplicate intent maps, domain semantic planners | низкий | **Recommended** |
| Regex + domain planners | CURRENT и протестирован | да/да | смешанная | почти ничего | локальный complexity lock-in | migration fallback |
| Agents SDK/ADK | зрелые, быстро меняются | да/да | tracing/session policy | часть glue, но не Core/effects | высокий | reject |
| PydanticAI | зрелый, частые releases | да/да | provider-dependent | gateway boilerplate | средний | reject |
| LangGraph | зрелый | да/да | local possible | switch/table, но добавляет checkpoint | средний | reject Gate 1 |
| faster-whisper local | CURRENT, 1.2.1 | да/да | offline, no per-call cost | сохраняет current code | низкий | **Primary ASR** |
| whisper.cpp | зрелый native | особенно Windows | offline | требует новый adapter | низкий | fallback candidate |
| Google STT | managed | network | cloud cost/region | может снять local compute | высокий | post-Gate 3 optional |

### ADOPT

- Pydantic `2.13.4`;
- native Structured Outputs конкретного provider;
- pytest/JSONL golden corpus;
- faster-whisper `1.2.1`.

### ADAPT

- trusted ingress и voice metadata;
- existing Calendar/Tasks/Drive/document actions как downstream adapter
  contracts;
- product effects, approval, idempotency, outbox, reconciliation;
- current regex parsers как temporary deterministic fallback и shadow oracle.

### BUILD

- `IntentEnvelope` и internal `SemanticProposal`;
- provider-neutral gateway;
- state/transition store;
- route/effect registry;
- safe errors;
- corpus/eval harness.

### REJECT/DEFER

- Agents SDK, ADK, PydanticAI, LangGraph в Gate 1 runtime;
- model tool/function execution;
- automatic cross-provider fallback;
- cloud ASR до Gate 3;
- diarization;
- vector/long-term conversational memory;
- free-form tool names, dict payloads и model-selected permissions.

## 10. Reusable code и ожидаемое сокращение

Непосредственно переиспользуются:

- `src/contracts/models.py`;
- `src/transport/telegram/gateway.py`, models, bindings и checkpoint stores;
- `src/voice/base.py`, `faster_whisper.py`, `service.py`, confirmation primitives;
- `src/application/durable_product.py`, `durable_runtime.py`,
  `durable_telegram_state.py`;
- `src/application/product_effects.py`, task/patch confirmations;
- `src/storage/sqlite_store.py`, `src/storage/outbox.py`;
- `src/integrations/google_calendar.py`, `google_tasks.py`, `google_drive.py`;
- owner file/workspace, Business Notes, Memory и research profiles;
- текущие adversarial/restart/idempotency tests.

После полного migration и доказательства parity можно убрать из Gate 1 path:

- ordered domain hint cascade;
- process-memory-only Google Tasks context;
- legacy `ParsedIntent.payload`;
- duplicate intent→agent map;
- LLM domain planners как первый semantic classifier;
- generic worker fallback для неизвестного natural intent.

Физическое удаление выполняется только отдельной implementation revision после
impact analysis и regression acceptance.

## 11. Идеальный PASS Gate 1

PASS означает одновременно:

- один strict/frozen/extra-forbid `IntentEnvelope`;
- closed domain/action/source/output/effect enums;
- native strict Structured Outputs только semantic proposal, `tools=[]`;
- exact one-question clarification;
- durable scope `(tenant, actor, chat, topic)` и TTL;
- text/voice semantic parity;
- отдельная transcript confirmation state;
- Core-owned route/effect authority;
- false external effect = 0 и tenant leak = 0;
- refusal/malformed/outage имеют разные safe outcomes;
- duplicate update и cancel race воспроизводимы;
- versioned golden corpus минимум 80 cases проходит deterministic assertions;
- slash fallback создаёт тот же envelope;
- L1/L2/L3 evidence связан с exact corpus/schema/prompt/provider versions.

## 12. Риски и открытые вопросы

| Риск | Последствие | Control / владелец |
|---|---|---|
| provider quality drift | рост неверных intent | version pin + corpus canary; Gate 0/1 |
| unsupported schema feature | request rejection | schema compilation test per provider |
| RU entity errors | неверный target/time | entity resolver + clarification |
| semantic confidence miscalibration | лишние/пропущенные questions | held-out calibration |
| local CPU saturation | Telegram latency | semaphore/queue/timeout/warm model |
| cloud ASR privacy | audio disclosure | disabled until Gate 3 |
| migration double-route | duplicate effect | shadow no-effects + one authority flag |
| stale frame | wrong follow-up | exact scope/TTL/revision/domain switch |
| context poisoning | tool/effect escalation | no tools + effect re-derivation |
| provider outage | feature loss | slash/closed fast path + typed degraded mode |

Нормативные thresholds ASR и semantic confidence нельзя честно выбрать без
локального held-out corpus. Архитектура задаёт поля и policy bands; конкретные
cutoffs являются Gate 1 calibration artifact и проходят L2/L3 до rollout.

## 13. Первичные источники и версии

### Model structured output, agents и data

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
  — strict schema, explicit refusal, incomplete outcomes, supported subset;
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
  — отдельная tool/function semantic surface;
- [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)
  — endpoint retention и ZDR limitations;
- [OpenAI prompt-injection architecture, 11 марта 2026](https://openai.com/index/designing-agents-to-resist-prompt-injection/)
  — ограничение impact/sinks;
- [OpenAI Agents SDK on PyPI, 0.19.0, 27 июля 2026](https://pypi.org/project/openai-agents/);
- [OpenAI Agents SDK tracing](https://openai.github.io/openai-agents-python/tracing/);
- [Gemini Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output);
- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling);
- [Google ADK on PyPI, 2.5.0, 16 июля 2026](https://pypi.org/project/google-adk/);
- [Google ADK repository](https://github.com/google/adk-python);
- [PydanticAI on PyPI, 2.19.0, 28 июля 2026](https://pypi.org/project/pydantic-ai/);
- [PydanticAI repository](https://github.com/pydantic/pydantic-ai);
- [LangGraph on PyPI, 1.2.9, 10 июля 2026](https://pypi.org/project/langgraph/);
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence);
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).

### Voice

- [faster-whisper releases, 1.2.1, 31 октября 2025](https://github.com/SYSTRAN/faster-whisper/releases);
- [faster-whisper repository/license](https://github.com/SYSTRAN/faster-whisper);
- [OpenAI Whisper release v20250625](https://github.com/openai/whisper/releases);
- [OpenAI Whisper repository/model notes](https://github.com/openai/whisper);
- [whisper.cpp release v1.9.1, 19 июня 2026](https://github.com/ggml-org/whisper.cpp/releases/tag/v1.9.1);
- [whisper.cpp repository/license/Windows](https://github.com/ggml-org/whisper.cpp);
- [Google Speech-to-Text supported languages: `ru-RU`](https://cloud.google.com/speech-to-text/v2/docs/speech-to-text-supported-languages);
- [Google Speech-to-Text data logging](https://cloud.google.com/speech-to-text/docs/data-logging);
- [Telegram Bot API: `Voice`, `getFile`, 20 MiB download limit](https://core.telegram.org/bots/api);
- [Telegram Bot API changelog](https://core.telegram.org/bots/api-changelog).

### Security и evals

- [OWASP LLM06: Excessive Agency](https://genai.owasp.org/llmrisk/llm06-excessive-agency/);
- [NIST AI 100-2e2025: adversarial ML taxonomy](https://csrc.nist.gov/pubs/ai/100/2/e2025/final);
- [MASSIVE multilingual intent/slot dataset](https://github.com/alexa/massive);
- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/);
- [Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/).

## 14. Verification evidence

### L1 — deterministic document checks

Проверяется: наличие всех нормативных sections, один `nobus.intent.v1`, closed
enums/limits, ровно 80 уникальных G01–G80, разрешимость внутренних Markdown
links, UTF-8, отсутствие token/cookie/private-key patterns и изменение только
двух разрешённых файлов. Это проверка dossier/архитектуры, не заявление о
готовности runtime.

### L2 — current-route walk и provider semantics

Corpus сопоставлен с CURRENT cascade: status/limits/help, research, Calendar,
Tasks, Drive/local documents, business notes, Nobus Memory и marketplace
планировщики имеют разные pre-parser/hint paths; поэтому oracle хранит отдельно
`expected_semantics` и `expected_gate_outcome`. Future/unavailable route обязан
вернуть `unsupported` и zero effects, а не считаться NLU error.

Официальные provider semantics подтверждают архитектурный boundary: strict
Structured Outputs обеспечивает schema adherence лишь в поддерживаемом subset;
refusal и incomplete являются отдельными outcome; function/tool calling — другая
поверхность. Следовательно, schema validation не заменяет semantic/effect/policy
validation, а tools в semantic call должны быть отключены.

### L3 — adversarial review matrix

| Threat/fault | Нормативный исход |
|---|---|
| prompt injection в owner text/document | content остаётся data; нет tools; Core re-derives effect |
| cross-topic/tenant follow-up | exact scope key; no frame match; zero route/effect |
| stale context | TTL + revision/CAS; expire/new intent |
| tool hallucination | protocol violation; никакой adapter не исполняется |
| effect escalation/third-party destination | fail-closed или один вопрос без предложения нового effect |
| ASR misrecognition | transcript confirmation; no semantic mutation до accept |
| refusal/malformed/incomplete output | typed safe error; effects=0; no write fallback |
| provider outage | typed degraded mode; slash и allowlisted read-only fallback only |
| duplicate update | shared idempotency; один task/effect |
| cancel/effect race | CAS + policy/effect gate + reconciliation; no blind duplicate |

Независимая L2/L3 проверка должна принять документ до `ARCHITECTURE READY`;
реализационные PASS-метрики остаются Definition of Done будущих slices.

## 15. Research disposition

Исследование не обнаружило blocker для нормативной архитектуры. Технические
unknowns — calibration thresholds, окончательный provider/model и cloud privacy
policy — намеренно вынесены в corpus evidence и Gate 3, а не маскируются
framework choice.

**RESEARCH READY**
