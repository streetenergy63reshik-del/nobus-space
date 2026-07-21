# Gate 4C — durable local SQLite store

**Status:** `ACCEPTED — L1/L2/L3 PASS`

## Scope

Изолированный stdlib-модуль без runtime-интеграции:

- `TrustedIngressEnvelope`, `TaskContract` и реальный runtime `Task` повторно
  валидируются на storage boundary;
- для нового ingress проверяется точная envelope ↔ contract ↔ task привязка;
- ingress claim и начальная recovery-проекция фиксируются одним
  `BEGIN IMMEDIATE` transaction;
- restart replay с новым server UUID/timestamp возвращает исходную проекцию по
  stable fingerprint и не создаёт вторую задачу;
- SQLite сохраняет frozen `DurableTaskProjection`: task/tenant/contract,
  source/risk/status, безопасную server identity исполнителя, result/output digests,
  типизированные `VerificationBundle`/`HumanApprovalRecord`, их истории и timestamps;
- raw `instruction`, chat ID, `payload`, `result`, `context`, error text, actor,
  content/auth refs не попадают ни в DB, ни в WAL;
- `save_task` — только CAS-обновление существующей записи с immutable bindings;
  отдельный insertion path отсутствует; переход проверяется общим Core
  `ensure_transition` и injected `TrustedVerifierRegistry`;
- result/output digests пересчитываются из runtime `result`/`context`; `REWORK`
  сохраняет номер ревизии, но очищает активные digests и архивирует ровно текущие
  verification/approval records без лишних элементов истории;
- executor остаётся immutable во всех состояниях, кроме валидного
  `REWORK → DRAFT` с новой запечатанной result revision;
- инвариант результата не классифицирует статусы: revision 0 не имеет digests;
  revision > 0 хранит активный result digest либо уже очищенный binding после
  валидного `REWORK`; необязательный `output_digest` не существует без result digest;
- initial claim принимает только точный результат
  `StateManager.create_from_contract`; claim binding отдельно связывает stable
  fingerprint, tenant/idempotency, task и contract digest;
- `WorkerEvent` append-only, строго упорядочен и tenant/task/contract/attempt/
  worker-bound; event ID уникален внутри tenant;
- чтение заново валидирует projection/event JSON, digest и все DB↔JSON bindings;
- ошибки повреждённой БД и недоступного path преобразуются в обезличенный
  `StoreCorruptionError` без path/raw exception chain.

Pickle, ORM, новые зависимости, сеть, subprocess и live Telegram отсутствуют.

Проекция достаточна, чтобы продолжить Core policy и аудит после restart, но не
восстанавливает raw runtime `Task`: исходная инструкция, payload, полный result,
context и error text намеренно не являются содержимым этого checkpoint.

## Manifest

- `src/storage/__init__.py`
- `src/storage/sqlite_store.py`
- `tests/test_sqlite_store.py`
- `docs/handoffs/GATE-4C.md`

## Executor checks

- target: `61 passed`;
- full suite: `365 passed, 1 warning`;
- crash-gap regression: failed ingress insert rolls back initial projection;
- restart replay: new UUID/time returns the originally bound task projection;
- real `StateManager.create_from_contract()` task with non-empty payload accepted,
  while raw operational fields are absent from DB/WAL;
- row/JSON tampering, tenant collision and malformed DB/path: safe rejection;
- policy recovery regression: PENDING → PARSING → DRAFT → L1 → L2 → L3 →
  COMPLETED with stored structured evidence;
- real DRAFT/L1/REJECTED → REWORK flows and forged history/result regressions;
- result without `output_digest`, DRAFT → DEFERRED → IN_PROGRESS → WAITING_INPUT,
  HIGH L1–L4 → EXECUTING → FAILED, and REWORK → new sealed DRAFT regressions;
- independent L3 regression slice: executor reassignment, result states,
  REWORK/history, claim binding and tamper scenarios: PASS;
- reviewer: `Codex independent review`; L1/L2/L3: PASS;
- L4: not required for this local module; runtime integration and live use are
  outside this Gate.
