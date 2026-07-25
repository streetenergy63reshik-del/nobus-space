# Queue 1/2 — accepted local release candidate

The local branch contains the restart-safe Telegram queue, confirmations, supervised
runner, strict backup/restore, public-web research and owner-bound document/download/
network effects. Local L1/L2/L3 are `ACCEPT`; it is not live and awaits one exact owner
L4 release package. Active semantics:
[docs/adr/0011-durable-owner-effects-and-web-profiles.md](docs/adr/0011-durable-owner-effects-and-web-profiles.md).

The readiness statements and test counts below this release-candidate header are historical snapshots. Where they conflict, this header, ADR 0011 and the leading section of `docs/handoffs/CURRENT-STATUS.md` are authoritative.

# Nobus Space — Telegram Orchestrator MVP

`nobus-orchestrator-dev` — единственный канонический репозиторий MVP платформы Nobus Space. Цель ближайшего релиза: безопасно принять текстовую или голосовую команду владельца в Telegram, показать понятное превью, создать проверяемую задачу, выполнить её через локальный worker и вернуть результат только после требуемых проверок.

Реализация MVP-1 завершена и независимо принята. Reliability-релиз `36c17e4` с обязательным startup probe реального Codex CLI, безопасными диагностическими кодами и тихим продуктовым UX активирован в `agent/telegram-live`: startup probe прошёл, polling lease получена, desktop-runner работает. Production-readiness (OS supervisor, monitoring, backup/restore и deployment) остаётся отдельным Gate 5B после функционального MVP-1.

## Текущее состояние

- Gate 0 и Documentation baseline приняты: `ea5bd51`, `364e6ab`.
- Gate 1–2: Core contracts/policy, Telegram ingress и безопасный voice preview приняты.
- Gate 3A/3B: Codex CLI boundary и Windows process-tree hardening приняты, включая `007640b`.
- Gate 4A–4F: trusted ingress, SQLite tasks/events/outbox, voice confirmation и durable recovery E2E приняты.
- Gate 5A.1–5A.3: authenticated owner-bound Telegram receive/send и live fake-task smoke приняты.
- Gate 5A.4: product text/voice UX, read-only Codex, verified answers, exact diff, L1/L2/L3, owner L4 и CAS commit приняты; reliability-релиз добавляет fail-fast startup probe и не показывает служебные подтверждения для обычных задач.
- Reliability verification: `127` target, `190 passed, 1 skipped` adversarial, `727 passed, 2 skipped, 1 warning` full; независимый verdict: `ACCEPT`, P0/P1/P2 отсутствуют.
- Gate 5B / Queue 1–2: локальный supervisor, health alerts, строгие backup/restore и durable effects реализованы в текущем unreleased release candidate; локальные L2/L3 дали ACCEPT; live-активация выполняется по уже выданному ограниченному L4.

Подробный воспроизводимый снимок: [docs/handoffs/CURRENT-STATUS.md](docs/handoffs/CURRENT-STATUS.md).

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

Gate 5A.4 соединяет authenticated Telegram ingress, обычный текст как задачу, voice transcription/confirmation, read-only Codex draft, exact diff, L1/L2/L3, owner-bound L4 и локальный CAS commit в изолированной ветке. Pre-apply journal и restart reconciliation предотвращают тихую потерю или дублирование эффекта. Runner остаётся desktop-процессом, а не production service.

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
