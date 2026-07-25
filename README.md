# Nobus Space — Telegram Orchestrator MVP-1

`nobus-orchestrator-dev` — единственный канонический репозиторий Nobus Space.
Локальный owner runtime `aa8a02e` принимает текстовые и голосовые задачи из
Telegram, выполняет их через изолированный Codex CLI, применяет L1/L2/L3 и
запрашивает L4 только для конкретного внешнего эффекта.

## Текущее состояние

- Gate 0–4F: contracts, policy, trusted Telegram/voice ingress, SQLite,
  verification, outbox и recovery — `ACCEPTED`;
- Gate 5A: owner-bound live Telegram, text/voice, `gpt-5.6-sol` high/Fast,
  `/limit` и `/file` — `ACCEPTED LIVE`;
- Gate 5B / Queue 1–2: durable FIFO, DPAPI confirmations/effects, progress card,
  public web research, owner-L4 documents/download/network, Task Scheduler,
  health и backup/restore — `ACCEPTED LOCAL OWNER RUNTIME`;
- полный release suite: `893 passed, 2 skipped`; независимые L2/L3 — `ACCEPT`;
- remote отсутствует; merge/rebase/push запрещены.

Это локальный owner runtime, а не внешний production deployment. Отдельная
Windows service identity/ACL, независимый monitoring, утверждённые RPO/RTO,
Google integrations и business-notes connector остаются TARGET.

Подробный воспроизводимый снимок:
[docs/handoffs/CURRENT-STATUS.md](docs/handoffs/CURRENT-STATUS.md).
## Документация

Канонический индекс: [docs/README.md](docs/README.md). В документах всегда разделены:

- `CURRENT` — подтверждённое поведение существующего кода;
- `TARGET` — обязательная целевая архитектура;
- статус решения (`CANONICAL`/ADR `ACCEPTED`) — правило, которое может быть ещё не реализовано.

## План MVP

```text
authenticated Telegram ingress
  -> text or voice preview
  -> explicit confirmation when needed
  -> trusted TaskContract
  -> persisted task and ordered WorkerEvents
  -> local Codex CLI worker
  -> result-bound L1 / L2 / L3 evidence
  -> L4 for every external mutation
  -> concise Telegram response
```

Текстовые задачи запускают read-only подготовку сразу. Голосовые задачи требуют подтверждения транскрипта. Любое изменение кода дополнительно требует owner-bound L4 и фиксируется только в `agent/telegram-live`; merge, push и внешние эффекты не выполняются.

## Структура

```text
src/
├── application/     # durable runtime, Telegram product UX и Gate 5A.4
├── agents/          # replaceable workers; сейчас только прототип AuditAgent
├── contracts/       # локальные versioned Core contracts
├── core/            # deterministic policy guards
├── memory/          # локальный codebase-search prototype
├── models/          # текущая runtime Task model
├── orchestrator/    # parsing, routing, graph and state manager
├── skills/          # rule-based helpers
├── storage/         # durable SQLite checkpoints/events/outbox
├── transport/       # Telegram normalization и ограниченный Bot API client
├── voice/           # bounded download, faster-whisper и confirmation
└── workers/         # read-only Codex CLI и exact patch parser
docs/                # каноническая документация и ADR
tests/               # unit, policy and API tests
```

Gate 5A.4 соединяет authenticated Telegram ingress, обычный текст как задачу, voice transcription/confirmation, read-only Codex draft, exact diff, L1/L2/L3, owner-bound L4 и локальный CAS commit в изолированной ветке. Pre-apply journal и restart reconciliation предотвращают тихую потерю или дублирование эффекта. Runner запускается Task Scheduler под текущим owner Windows account; это host-local runtime, а не production service identity.

## Локальная проверка

Требуется Python 3.12. Виртуальное окружение создаётся локально и не добавляется в Git.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -q
```

Если Python 3.12 недоступен, окружение считается неподготовленным; не следует подменять это production-ready инструкцией.

## Безопасность разработки

- Не записывать в репозиторий Telegram token, API keys, credentials, cookies, `.env`, сырые voice-файлы, логи или клиентские данные.
- Не считать `.env` защищённым secret store.
- Не выполнять push, deploy, публикацию и внешние изменения без отдельного явного подтверждения владельца.
- Любой результат остаётся `DRAFT` до независимых L1/L2/L3; все внешние записи дополнительно требуют связанного L4.
- При rework старая ревизия результата и её доказательства не переиспользуются.

Локальные правила исполнителей: [AGENTS.md](AGENTS.md).
