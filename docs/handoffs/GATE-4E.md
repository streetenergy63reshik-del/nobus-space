# Gate 4E — durable local status outbox

**Status:** `ACCEPTED — L1/L2/L3 PASS`

## Scope

Изолированный локальный модуль без сети и реальной отправки в Telegram:

- переход `Task` и постановка status-notification сохраняются одной SQLite-транзакцией;
- idempotency связывает полный digest durable-проекции Task, её revision, tenant, destination reference и шаблон сообщения;
- outbox не хранит raw instruction, payload, transcript, chat text, result text, error text или credentials;
- `destination_ref` допускается только как `sha256:` reference, а шаблон ограничен `task_status`;
- claim tenant-scoped, выдаёт post-update lease с новым UUID generation и ограничен 100 элементами;
- lease имеет server-owned UTC time, срок от 1 до 3600 секунд и не может превысить `max_attempts`;
- просроченный lease восстанавливается после restart; последний исчерпанный attempt переходит в `failed`;
- ACK/NACK/TIMEOUT принимается только для точной текущей generation, owner и attempt;
- receipts append-only и повторно проверяются по typed JSON, digest и реляционным binding;
- row/JSON/digest mismatch и некорректные lifecycle updates отклоняются безопасными типизированными ошибками;
- существующая Gate 4C сериализация non-UTC aware timestamps сохранена без миграции и изменения digest;
- новые outbox/receipt timestamps нормализуются в UTC, naive timestamps запрещены.

Gate 4E не подключён к runtime, Telegram client или network transport. Он не отправляет сообщения и не выполняет внешних действий.

## Manifest

- `src/storage/__init__.py`
- `src/storage/outbox.py`
- `src/storage/sqlite_store.py`
- `tests/test_sqlite_outbox.py`
- `tests/test_sqlite_store.py`
- `docs/handoffs/GATE-4E.md`
- `.nobus-quality/cases.ndjson`

## Verification

- L1 target Gate 4C + 4E: `110 passed`;
- L2 full suite: `414 passed, 1 warning`;
- `pip check`: `No broken requirements found.`;
- `python -m compileall`: PASS;
- `git diff --check`: PASS, только информационное LF→CRLF notice Git;
- независимый reviewer воспроизвёл первоначальные defects, проверил rework и вернул `ACCEPT`;
- новые adversarial regressions покрывают full-projection replay binding, mixed UTC offsets, stale lease generation, receipt corruption, concurrent duplicate enqueue, retry ceiling, tenant scope и FK preservation;
- L4 не требуется: отсутствуют credentials, сеть, реальная отправка, deployment, remote и другие внешние записи.

Ожидаемое предупреждение полного suite осталось прежним: `StarletteDeprecationWarning` о будущем переходе TestClient на `httpx2`.

## Rejected predecessor

Web artifacts E1–E3 использованы только как требования и материал ревью. E3 patch не переносился: локальное воспроизведение показало regressions и несогласованные lifecycle semantics. Gate 4E реализован заново поверх принятого Gate 4C baseline `b9bf559`.

## Next boundary

Следующий автономный блок — Gate 4F: wiring принятого SQLite store/outbox в локальный fake runtime и restart/recovery E2E. Реальный Telegram transport, bot token, polling/webhook и отправка сообщений остаются за отдельным L4.
