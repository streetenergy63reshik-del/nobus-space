# Nobus Space MVP-1 — актуальный статус архитектурной итерации

**CURRENT на 1 августа 2026 года:** Gate 0 READY, sealed `22/22` и принят
отдельным immutable acceptance commit.

result_commit: f5086b2a71a9ae22be3c858ff69453287f6925da
result_tree: 2e3248eb295b1627d36f196c26dfc21c6ebd90fd

- замечания независимого аудита закрыты в Product Contract/corpus v2,
  digest-bound normative catalog, ADR 0020, Gate 2A и domain `development`;
- независимые L1/L2/L3 привязаны к exact candidate и trusted canonical runtime;
- Gate 1 больше не заблокирован predecessor Gate 0, но требует собственного
  change manifest, проверок и acceptance;
- Gate 2 начинается только после принятого Gate 1; SSH/VPS впервые требуются
  не для Gate 1–2, а для отдельной live-активации Gate 2A;
- в репозитории пока нет настроенного Git remote; push и deploy не выполнялись.

Точный текущий источник статуса: [Gate 0 acceptance](docs/gates/gate-00-product-contract-baseline/GATE-0-ACCEPTANCE.json),
[Gate 0 HANDOFF](docs/gates/gate-00-product-contract-baseline/HANDOFF.md) и
[audit remediation record](docs/gates/gate-00-product-contract-baseline/INDEPENDENT-AUDIT-REMEDIATION.md).
Каноническая навигация: [индекс документации](docs/README.md) и
[пакет Gate 0–8](docs/gates/README.md). Действия владельца после Gate 0,
включая разделение Git SSH, VPS SSH и Gate 2A, собраны в
[owner-runbook](docs/14-Действия-владельца-после-Gate-0-SSH-VPS-и-Gate-1-2.md).

## Архив: локальная runtime-итерация до текущей дорожной карты Gate 0–8

> Все статусы, Gate-номера, commits и runtime-утверждения ниже относятся только
> к предыдущей локальной итерации и не определяют CURRENT для Gate 0–8.

Feature commit `33b35f7` replaces the one-shot `codex exec --json/ephemeral`
production worker with the official persistent `openai-codex` SDK/app-server.
It adds separate resumable threads for the owner chat and Telegram topics,
`gpt-5.6-sol/high/Fast`, a three-hour task deadline, bounded cancellation,
complete Google Tasks pagination, durable voice recovery and exact owner-command
authorization while preserving application-owned snapshot/diff/atomic effects.
The clean-worktree L2 reproduction is `1088 passed, 2 skipped`; the focused L3
fault-injection slice is `208 passed, 2 skipped`. Live publication is not claimed
until the backup/switch/startup-probe/owner-smoke sequence is complete. Active
semantics:
[ADR 0016](docs/adr/0016-persistent-mobile-codex-runtime.md).

The readiness statements and test counts in this historical snapshot describe
the preceding local-runtime iteration. For the current Gate 0–8 architecture
iteration, the leading section of this README and the sealed Gate 0 handoff are
authoritative.

### Историческая сводка локального Telegram Orchestrator MVP

На момент этого snapshot `nobus-orchestrator-dev` использовался как канонический репозиторий локального MVP платформы Nobus Space. Целью той итерации было безопасно принять текстовую или голосовую команду владельца в Telegram, показать понятное превью, создать проверяемую задачу, выполнить её через локальный worker и вернуть результат только после требуемых проверок.

В той итерации функциональный MVP-1 был объявлен завершённым и независимо принятым. Reliability-релиз `36c17e4` с обязательным startup probe реального Codex CLI, безопасными диагностическими кодами и тихим продуктовым UX был активирован в `agent/telegram-live`: startup probe прошёл, polling lease была получена, desktop-runner работал. Эти сведения не доказывают CURRENT topology новой дорожной карты; отдельная telegram-live isolation остаётся TARGET соответствующего runtime/deployment Gate.

### Историческое состояние предыдущей итерации

- Прежние Gate 0 и Documentation baseline были приняты в `ea5bd51` и `364e6ab`.
- Прежние Gate 1–2 включали Core contracts/policy, Telegram ingress и voice preview.
- Прежние Gate 3A/3B включали Codex CLI boundary и Windows process-tree hardening, включая `007640b`.
- Прежние Gate 4A–4F включали trusted ingress, SQLite tasks/events/outbox, voice confirmation и durable recovery E2E.
- Прежние Gate 5A.1–5A.3 включали authenticated owner-bound Telegram receive/send и live fake-task smoke.
- Прежний Gate 5A.4 включал product text/voice UX, read-only Codex, verified answers, exact diff, L1/L2/L3, owner L4 и CAS commit.
- Историческая reliability verification: `127` target, `190 passed, 1 skipped` adversarial, `727 passed, 2 skipped, 1 warning` full; verdict `ACCEPT`, P0/P1/P2 отсутствовали.
- Прежний Gate 5B / Queue 1–2 описывал локальный supervisor, health alerts, backup/restore и durable effects в unreleased candidate.

Этот архив не является CURRENT authority. Точный статус текущего Gate 0 находится
в [запечатанном HANDOFF](docs/gates/gate-00-product-contract-baseline/HANDOFF.md),
а подробная хронология прежнего runtime — в
[историческом CURRENT-STATUS](docs/handoffs/CURRENT-STATUS.md).

### Документация исторического snapshot

Канонический индекс: [docs/README.md](docs/README.md). В документах всегда разделены:

- `CURRENT` — подтверждённое поведение существующего кода;
- `TARGET` — обязательная целевая архитектура;
- статус решения (`CANONICAL`/ADR `ACCEPTED`) — правило, которое может быть ещё не реализовано.

### План исторического snapshot

```text
authenticated Telegram ingress
  -> text or voice preview
  -> explicit confirmation when needed
  -> trusted TaskContract
  -> persisted task and ordered WorkerEvents
  -> persistent official Codex SDK/app-server
  -> result-bound L1 / L2 / L3 evidence
  -> L4 for every external mutation
  -> concise Telegram response
```

Текстовые задачи запускают read-only подготовку сразу. Голосовые задачи требуют подтверждения транскрипта. Любое изменение кода дополнительно требует owner-bound L4 и фиксируется только в `agent/telegram-live`; merge, push и внешние эффекты не выполняются.

### Структура исторического snapshot

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
└── workers/         # persistent Codex SDK, legacy boundary и exact patch parser
docs/                # каноническая документация и ADR
tests/               # unit, policy and API tests
```

Gate 5A.4 соединяет authenticated Telegram ingress, обычный текст как задачу, voice transcription/confirmation, read-only Codex draft, exact diff, L1/L2/L3, owner-bound L4 и локальный CAS commit в изолированной ветке. Pre-apply journal и restart reconciliation предотвращают тихую потерю или дублирование эффекта. Runner остаётся desktop-процессом, а не production service.

### Локальная проверка исторического snapshot

Требуется Python 3.12. Виртуальное окружение создаётся локально и не добавляется в Git.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -q
```

Если Python 3.12 недоступен, окружение считается неподготовленным; не следует подменять это production-ready инструкцией.

### Безопасность разработки исторического snapshot

- Не записывать в репозиторий Telegram token, API keys, credentials, cookies, `.env`, сырые voice-файлы, логи или клиентские данные.
- Не считать `.env` защищённым secret store.
- Не выполнять push, deploy, публикацию и внешние изменения без отдельного явного подтверждения владельца.
- Любой результат остаётся `DRAFT` до независимых L1/L2/L3; все внешние записи дополнительно требуют связанного L4.
- При rework старая ревизия результата и её доказательства не переиспользуются.

Локальные правила исполнителей: [AGENTS.md](AGENTS.md).
