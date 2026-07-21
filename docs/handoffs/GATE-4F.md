# Gate 4F — durable local runtime wiring

**Статус:** ACCEPTED — L1/L2/L3 PASS
**Дата:** 2026-07-21
**Implementation commit:** `a56bdf3 feat: wire durable local orchestrator runtime`
**L4:** не требовался: только локальный fake/injected контур без сети, credentials, live subprocess, deploy и внешней записи

## Принятый scope

- `DurableFakeRuntime` связывает trusted text ingress и подтверждённый voice preview с Core, SQLite, fake worker, injected L1/L2/L3 и durable status outbox;
- ingress claim и начальный Task сохраняются атомарно; повтор после restart возвращает исходный Task без повторного worker;
- Task transitions `PARSING`/`DRAFT` атомарно связаны с `STARTED`/`RESULT_READY` WorkerEvents;
- worker exception атомарно создаёт safe `FAILED` event, terminal Task и status outbox без raw exception;
- terminal `COMPLETED`/`REJECTED`/`FAILED`/`ESCALATE` атомарно ставятся в outbox;
- StateManager выполняет storage-first callback: отказ durable write не продвигает in-memory Task;
- voice confirmation возвращает точный исходный trusted voice envelope; transcript/token/raw audio не сохраняются в SQLite;
- restart завершённой задачи не повторяет worker; незавершённая задача получает `RECOVERY_REQUIRED`;
- injected sender использует bounded outbox lease и ACK/NACK receipts; cancellation безопасно оставляет lease для reclaim;
- tenant allowlist и exact `destination_ref` проверяются до sender; stale destination получает NACK без отправки;
- SQLite read/init connections закрываются явно.

## Transaction boundaries

1. `claim_ingress_with_task`: trusted ingress + initial Task.
2. `save_task_and_append_event`: Task transition + ordered WorkerEvent.
3. `save_task_and_enqueue_status`: terminal Task + outbox; при worker failure дополнительно тот же `FAILED` WorkerEvent.
4. `record_outbox_receipt`: lease generation + ACK/NACK lifecycle.

Ни одна из этих операций не выполняет сеть или live subprocess.

## Recovery semantics

- durable `COMPLETED`/terminal Task восстанавливается без повторного исполнения;
- preterminal Task не возобновляется вслепую и требует явного reconciliation;
- pending voice challenge, update/callback claims, StateManager и PolicyStore остаются process-memory;
- transient failure до durable claim требует restart, а для voice может потребовать новый preview/confirm;
- delivery имеет at-least-once semantics: live adapter будущего Gate обязан использовать idempotency key;
- stale destination NACK требует operator reconciliation;
- автоматический resume, production capacity management и durable confirmation store не входят в Gate 4F.

## Изменённые implementation-файлы

- `src/application/__init__.py`
- `src/application/durable_runtime.py`
- `src/application/fake_vertical.py`
- `src/orchestrator/state_manager.py`
- `src/storage/sqlite_store.py`
- `src/voice/confirmation.py`
- `tests/test_durable_runtime.py`
- `tests/test_sqlite_store.py`

## Проверка

```text
Gate 4F target:                 14 passed
Gate 4C–4F relevant:          135 passed
Full repository:              475 passed, 1 warning
compileall:                   PASS
pip check:                    No broken requirements found.
git diff --check:             PASS (только Windows LF→CRLF notices)
Independent L3:              ACCEPT; P0=0, P1=0
```

Adversarial review воспроизвёл worker exception и подтвердил: Task `FAILED`, events `[STARTED, FAILED]`, outbox status `FAILED`, внутренний provider detail отсутствует. Проверены crash rollback, restart without rerun, voice replay, callback actor binding, tenant/destination isolation, outbox lease reclaim и отсутствие transcript/token/audio в SQLite.

Единственное предупреждение полного pytest осталось прежним: `StarletteDeprecationWarning` о будущем переходе TestClient на `httpx2`.

## Следующая граница

Локальная автономная очередь Gate 4A–4F завершена. Gate 3B/5A подключает live process и authenticated Telegram receive/send и требует отдельного L4 до credentials, сети, реальной отправки или внешних эффектов.