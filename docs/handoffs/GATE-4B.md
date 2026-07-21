# Gate 4B — trusted ingress contract

**Статус:** ACCEPTED — L1/L2/L3 PASS

**Дата проверки исполнителем:** 2026-07-21

## Реализовано

- `TrustedIngressEnvelope v1` — строгий immutable contract с закрытыми `source` и `kind`, server-owned actor binding, aware UTC time и самопроверяемым SHA-256 revision.
- Единственный рабочий путь выпуска Telegram envelope находится внутри `TelegramGateway.process_update(raw_update)`. Отдельный factory-модуль удалён; callable, принимающего naked normalized payload вместе с binding для выпуска envelope, нет.
- Server UUID и aware time генерируются и валидируются до claim `update_id` и callback token. Ошибка, исключение или неверный тип не расходуют claims, поэтому тот же update можно безопасно повторить.
- После claims построение envelope использует только уже проверенные immutable данные и детерминированный canonical JSON digest; fallible injected dependency больше не вызывается.
- `TrustedIngressResult` повторно доказывает полное соответствие envelope payload: `update_id`, tenant, actor identity/role, auth context, source, kind, user/chat/message/callback identity, idempotency derivation и digest точного text/voice/callback content.
- Весь fallible parse/model/digest/result pipeline завершается до claims. После этого выполняются только атомарные claims в порядке update → callback и возвращается заранее построенный immutable result.
- `received_at` нормализуется в UTC до построения envelope; offset-aware часы дают один канонический момент времени.
- `external_message_id` включает update, user, chat и message/callback identity. `idempotency_key` дополнительно связан с actor identity/role, tenant, source и kind.
- Raw text, callback token и voice file id не сохраняются в envelope: хранится только `content_ref`.
- `InMemoryPolicyStore.register_contract(contract, envelope)` требует envelope для любого source, повторно валидирует обе модели и до мутации сверяет source, tenant, idempotency key и ingress digest. No-envelope API удалён.
- Local fake vertical получает envelope только из результата gateway и регистрирует contract вместе с ним.
- Runtime `Task` сохраняет ingress digest и ingress idempotency key вместе с существующими immutable bindings.

## Исправленные P1 и регрессии

1. Удалён второй путь minting через `src/transport/telegram/trusted.py`.
2. Mutated payload с прежним envelope отклоняется для text, voice и callback, включая identity и content mutations.
3. Исключения и invalid output UUID/clock возвращают безопасный `REJECTED`; повтор callback подтверждает отсутствие потери update/token claim.
4. API и остальные contract sources больше нельзя зарегистрировать без точного trusted envelope; невалидная попытка не оставляет частичной записи.
5. Oversized callback identity и другие model/digest failures возвращают безопасный `REJECTED`, не расходуют update/callback claims и допускают исправленный retry с теми же идентификаторами.

## Проверки и независимая приёмка

- Gate 4B target: `176 passed`.
- Полный pytest общей рабочей копии при `DEBUG=false`: `354 passed, 1 warning`, включая параллельный draft Gate 4C.
- Независимый adversarial-срез: `20 passed`.
- Reviewer: `Codex independent review`; L1/L2/L3: PASS.
- `git diff --check`: PASS; только уведомления Git о будущем LF→CRLF.
- Запрещённые network/live subprocess вызовы, новые зависимости, staging и commit отсутствуют.

## Ограничения

- Gate доказывает локальную config-bound привязку, но не подлинность Telegram webhook/polling update на сетевой границе.
- Actor bindings и callback/update claims пока in-memory; crash/restart durability относится к Gate 4C.
- Загрузка Telegram-файла, реальная транскрипция и подтверждение voice preview не входят в Gate 4B.
- Внешние записи и действия не выполняются; L4 для этого локального draft не требуется.
- Реализация принята после независимых L1/L2/L3; live-boundary по-прежнему требует отдельного Gate и L4.

## Manifest draft

- `src/contracts/models.py`
- `src/contracts/__init__.py`
- `src/core/policy.py`
- `src/transport/telegram/models.py`
- `src/transport/telegram/gateway.py`
- `src/transport/telegram/__init__.py`
- `src/application/fake_vertical.py`
- `src/orchestrator/state_manager.py`
- `tests/test_contracts.py`
- `tests/test_telegram_gateway.py`
- `tests/test_trusted_ingress.py`
- `tests/test_fake_vertical.py`
- `tests/test_codex_cli.py`
- `docs/handoffs/GATE-4B.md`
