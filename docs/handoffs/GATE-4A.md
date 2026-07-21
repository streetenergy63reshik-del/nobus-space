# Gate 4A — local fake vertical E2E

**Статус:** ACCEPTED — L1/L2/L3 PASS

**Дата:** 2026-07-21

**Commit:** `dfc2e66 feat: add local fake Telegram vertical`

## Контракт результата

Цель Gate 4A — доказать полностью локальный text flow через уже существующие
границы без Telegram API, bot token, live subprocess, сети, новых зависимостей
и внешней записи.

Проверяемый поток:

```text
raw Telegram update
  -> TelegramGateway
  -> server-owned TaskContract
  -> InMemoryPolicyStore idempotency
  -> StateManager.create_from_contract
  -> injected fake CodexCliAdapter spawner
  -> DRAFT
  -> injected L1 -> injected L2 -> injected L3
  -> Core registry/policy validation
  -> COMPLETED for LOW
  -> immutable safe response
```

## Реализовано

- `StateManager.create_from_contract()` повторно валидирует `TaskContract` и
  атомарно создаёт runtime Task с теми же `task_id`, `tenant_id` и вычисленным
  `task_contract_digest`; старый `create()` не изменён.
- Текст Telegram становится только `instruction`. Пути, permissions, risk,
  timeout, quality profile и acceptance criterion задаются серверной
  композицией.
- Контракт регистрируется в tenant-scoped `InMemoryPolicyStore` до запуска
  worker. Повтор update не запускает второй worker/effect.
- Используется существующий `CodexCliAdapter` только с внедрённым fake spawner.
  Live process implementation не добавлена.
- Raw worker message не сохраняется и не возвращается: runtime result содержит
  фиксированный summary и SHA-256 digest сообщения. Он существует только в
  immutable ephemeral `VerificationInput`, чтобы каждый verifier проверял
  фактическое содержание одной и той же result revision.
- L1/L2/L3 являются тремя отдельными injected verifier boundaries. Они сами
  поставляют identity, method, timestamp и evidence; application слой не
  фабрикует evidence. `StateManager` и `TrustedVerifierRegistry` проверяют роли,
  последовательность, независимость identities/evidence и binding к
  task/tenant/contract/result.
- Failed verifier evidence переводит задачу в `REJECTED`; exception или
  malformed verifier result — в безопасный `ESCALATE`; worker failure — в
  `FAILED`. Ни один отказ не выдаёт `COMPLETED` и не возвращает raw exception.
- Voice возвращает `needs_voice_preview`, callback — `unsupported`; download,
  transcription и callback effect не запускаются.
- Ответ — frozen strict Pydantic model с фиксированными безопасными сообщениями.
- Ошибка server-owned contract configuration преобразуется в фиксированный
  `FAILED` до worker/verifier и не раскрывает путь или ValidationError.

## L1 — воспроизводимые проверки исполнителя

Среда:

```text
DEBUG=false
TEMP/TMP=C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\Code\test-temp-review-d59abf42309b4fec8f3442f5d64a85d8
```

Результаты:

```text
pytest tests/test_fake_vertical.py -q --disable-warnings
10 passed

pytest -q --disable-warnings
262 passed
```

В полном наборе остаётся известный `StarletteDeprecationWarning`; sandbox может
дополнительно сообщать о недоступном `.pytest_cache`, поэтому количество
предупреждений не является acceptance-метрикой Gate.

Target regressions проверяют:

- точные task/tenant/contract/result bindings;
- server-owned capabilities при hostile user text;
- duplicate update без второго worker call;
- distinct и role-allowlisted verifier identities;
- failed verifier evidence и verifier exception;
- worker exception с secret/path marker;
- worker output с secret/path marker доступен всем verifier boundaries, но не
  попадает в Task/response; evidence digest зависит от проверяемого результата;
- invalid server-owned path даёт безопасный FAILED без worker/verifier;
- immutable response;
- voice/callback без worker/verifier calls;
- только injected fake spawner.

## Изменённые файлы

```text
src/application/__init__.py
src/application/fake_vertical.py
src/orchestrator/state_manager.py
tests/test_fake_vertical.py
docs/handoffs/GATE-4A.md
```

`requirements.txt`, Telegram/voice/worker реализации, README, docs 01–10,
CURRENT-STATUS и `.nobus-quality/**` не изменялись в рамках Gate 4A.

## Ограничения и стоп-границы

- Это демонстрационная in-memory композиция, не production service.
- Actor и verifier identities приходят из injected локальной конфигурации;
  authenticated Telegram/Core boundary ещё отсутствует.
- Нет persistence, crash recovery, cross-process transaction и durable queue.
- Raw worker result намеренно доступен только как digest; пользовательский
  preview/result delivery — отдельный контракт после policy redaction.
- Voice требует отдельного подтверждённого preview flow.
- Callback не исполняет approval или внешний эффект.
- Реальный Telegram token/network, live Codex process, OS sandbox expansion,
  deploy, remote/push и внешние записи остаются запрещены до отдельных Gate/L4.

## Ponytail review

Добавлена одна application composition и один необходимый Core constructor.
Не добавлены DI framework, queue, repository abstraction, production API,
live adapters или новая dependency. Удалить без потери требований можно только
handoff; production код уже является минимальной связкой существующих границ.

## Независимая проверка

- L1: PASS исполнителем, результаты выше.
- L2: PASS — target и full suite независимо воспроизведены.
- L3: PASS — invalid configuration, result/evidence binding, replay,
  cancellation, mutation, false completion и leakage проверены adversarial.
- L4: не требуется для локальной fake-only реализации; потребуется перед
  credentials, сетью, live process, внешней записью или deployment.
