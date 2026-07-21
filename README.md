# Nobus Space — Telegram Orchestrator MVP

`nobus-orchestrator-dev` — единственный канонический репозиторий MVP платформы Nobus Space. Цель ближайшего релиза: безопасно принять текстовую или голосовую команду владельца в Telegram, показать понятное превью, создать проверяемую задачу, выполнить её через локальный worker и вернуть результат только после требуемых проверок.

Проект находится в разработке и не готов к автономной production-эксплуатации.

## Текущее состояние

- Gate 0: локальный baseline `ea5bd51` принят.
- Documentation baseline: канонический комплект 01–10 и ADR 0001–0008 принят в `364e6ab`.
- Gate 1: contracts/state/completion policy принят в `7b92978`.
- Gate 2: Telegram ingress и безопасный bytes-only voice preview приняты в `5df4ccd`.
- Gate 3A: fake-only Codex CLI boundary принят в `294047c`; live process не подключён.
- Gate 4A: локальный text-only fake E2E принят в `dfc2e66`.
- Gate 4B: trusted ingress envelope и обязательная привязка к `TaskContract` приняты в `2afd880`.
- Gate 4C: изолированные durable SQLite checkpoints и append-only events приняты в `d775699`; runtime wiring ещё не выполнен.
- Gate 4E: локальный durable status outbox принят в `afb6859`; runtime/Telegram wiring ещё не выполнен.

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

Сначала собирается полностью локальный сценарий на fake adapters. Токены, сетевые вызовы, публикация, deploy, деньги, удаление и изменение внешних систем не входят в автономные ночные работы.

## Структура

```text
src/
├── agents/          # replaceable workers; сейчас только прототип AuditAgent
├── contracts/       # локальные versioned Core contracts
├── core/            # deterministic policy guards
├── memory/          # локальный codebase-search prototype
├── models/          # текущая runtime Task model
├── orchestrator/    # parsing, routing, graph and state manager
├── skills/          # rule-based helpers
├── storage/         # локальные durable SQLite checkpoints; пока не wired в runtime
├── transport/       # Telegram normalization, без сетевого клиента
├── voice/           # bytes-only preview и provider boundary
└── workers/         # fake-only Codex CLI boundary
docs/                # каноническая документация и ADR
tests/               # unit, policy and API tests
```

Text-компоненты Gate 1–4B соединены только в локальный fake-сценарий. Gate 4C добавляет проверенное SQLite-хранилище как отдельный модуль, но ещё не подключает его к runtime. Это не означает authenticated Telegram API, live Codex process или production-доступа.

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
