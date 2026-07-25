# ADR 0016 — persistent mobile Codex runtime

**Статус:** ACCEPTED
**Реализация:** RELEASE CANDIDATE
**Дата:** 2026-07-25

## Контекст

Одноразовый `codex exec --json --ephemeral` терял диалоговый контекст,
требовал самописного JSONL-парсера и плохо подходил для длительных Telegram-задач.
Одновременно прямой `workspace-write` модели нарушил бы обязательные snapshot,
diff, атомарную запись, rollback и отдельный запрет удаления.

## Решение

1. Production worker использует официальный `openai-codex` SDK/app-server
   версии `0.144.4` и закреплённый runtime `openai-codex-cli-bin==0.144.4`.
2. Модель — `gpt-5.6-sol`, reasoning `high`, service tier `fast`.
3. Для личного чата и каждой Telegram-темы используется отдельный именованный
   non-ephemeral Codex thread. После restart thread возобновляется по имени.
4. Model-turn всегда запускается в OS sandbox `read-only` с `deny_all`.
   Web search включается только в research-profile.
5. Записи остаются application-owned: owner-команда создаёт типизированное
   предложение, а доверенный adapter применяет его со snapshot/diff/atomic/CAS.
   Удаление пользовательских файлов не разрешается общей командой.
6. Длительная задача имеет deadline 10 800 секунд, app-server ceiling —
   14 400 секунд. Telegram polling и durable queue не ждут завершения turn.
7. Interrupt, close и thread-list pagination ограничены отдельными control
   timeout/limit, чтобы повреждённый app-server не блокировал supervisor.
8. Google retry разрешён только для идемпотентного чтения. Create/update/delete
   выполняются без транспортного retry; повтор определяется action-level
   idempotency и reconciliation.

## Последствия

- Nobus сохраняет разговорный контекст между сообщениями и перезапусками.
- Telegram topics и owner-private chat не смешивают threads.
- SDK не получает необусловленное право записи; Core остаётся владельцем effects.
- Нужны живой startup probe, локальный app-server health и rollback.
- Отдельная Windows service identity остаётся production-hardening: текущий
  локальный owner-runtime работает под подтверждённым Windows-пользователем.
