# ADR 0009. Telegram intake отделён от длительного Codex execution

**Статус:** ACCEPTED
**Дата:** 2026-07-23
**Реализация:** PARTIAL; main проверяется, live activation требует отдельного owner L4

## Контекст

Telegram handler последовательно ожидал read-only Codex worker. Поэтому одна задача блокировала следующие update/callback, а прежний execution deadline 120 секунд противоречил реальным задачам длительностью до двух часов. Владельцу нужен приём серии из 3–5 text/voice задач без ожидания завершения предыдущей.

## Решение

1. Telegram polling и worker execution имеют разные lifecycle и deadline. Accepted text и подтверждённый voice ставятся в FIFO-очередь и сразу освобождают handler.
2. Локальный MVP использует два параллельных read-only executor-слота без нового broker/dependency.
3. Owner-confirmed exact diff, L2/L3, apply и локальный CAS commit получают эксклюзивный доступ к обоим слотам.
4. Production CLI profile фиксируется exact argv: `gpt-5.6-sol`, `model_reasoning_effort=high`, `service_tier=fast`, `features.fast_mode=true`; `workspace-write`, web и MCP запрещены.
5. Gate 5A.4 execution deadline равен 10 800 секундам: два часа ожидаемой работы плюс час operational headroom. Абсолютный TaskContract/adapter ceiling равен 14 400 секундам. Polling lease 240 секунд относится только к Telegram boundary.
6. Очередь CURRENT хранится в памяти owner-bound процесса: не более 32 ожидающих drafts, общий maxsize 40 с резервом для L4. Overflow и controlled close завершают каждый принятый active/queued job только после чтения exact terminal binding из durable store; ответ runtime сам по себе доказательством не считается. После трёх неудачных попыток admission не подтверждается либо clean shutdown завершается ошибкой. Новый message broker не вводится до Gate 5B.

## Последствия

- Пользователь может быстро передать несколько задач; две выполняются параллельно, остальные ждут FIFO.
- Fast mode сокращает latency, но увеличивает расход OpenAI credits; `high` сохраняет требуемую глубину reasoning.
- Две параллельные CLI-сессии увеличивают пиковое потребление CPU/RAM и credits, поэтому concurrency является server-owned константой, а не пользовательским параметром.
- Controlled restart разрешён только после остановки intake и опустошения очереди. При раннем shutdown active и queued jobs получают bounded terminalization retry; clean close требует повторного чтения exact terminal Task из SQLite. Crash не replay-ит незапущенные raw instructions; durable Task/audit/outbox остаются fail-closed и требуют reconciliation.
- Durable claim/lease queue, rate limits, supervisor и restart resume остаются Gate 5B.

## Проверка

Обязательны: exact-argv regression, schema/adapter timeout boundaries, пять быстрых ingress updates при двух заблокированных workers, три queued jobs, status counters, false `REJECTED` без durable write, persistent overflow без polling ACK, active/pending close cleanup, реальные Gate wrapper tests, полный pytest и независимый L2/L3 review. Live startup probe и перезапуск являются отдельным L4.
