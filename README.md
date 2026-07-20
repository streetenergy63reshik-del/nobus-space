# Nobus Space — Telegram Orchestrator MVP

`nobus-orchestrator-dev` — единственный канонический репозиторий MVP платформы Nobus Space. Цель ближайшего релиза: безопасно принять текстовую или голосовую команду владельца в Telegram, показать понятное превью, создать проверяемую задачу, выполнить её через локальный worker и вернуть результат только после требуемых проверок.

Проект находится в разработке и не готов к автономной production-эксплуатации.

## Текущее состояние

- Gate 0: локальный baseline `ea5bd51` принят.
- Gate 1: contracts/state policy существует как незакоммиченный draft; независимый аудит выявил критические обходы привязки результата и доказательств, поэтому статус — **REWORK**.
- Gate 2A: Telegram ingress принят в изолированном commit `8478a77`, но ещё не интегрирован в `main`.
- Gate 2B: voice preview принят в изолированном commit `227076d`, но ещё не интегрирован в `main`.
- Gate 3: безопасный Codex CLI adapter не реализован.
- Gate 4: сквозной fake-сценарий не собран; реальный Telegram bot не подключался.

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
├── contracts/       # versioned Core contracts (Gate 1 draft)
├── core/            # deterministic policy guards (Gate 1 draft)
├── memory/          # локальный codebase-search prototype
├── models/          # текущая runtime Task model
├── orchestrator/    # parsing, routing, graph and state manager
└── skills/          # rule-based helpers
docs/                # каноническая документация и ADR
tests/               # unit, policy and API tests
```

Telegram/voice файлы пока находятся только в отдельной локальной ветке и появятся в этой структуре после контролируемой интеграции.

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
