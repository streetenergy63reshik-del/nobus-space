# Nobus Space MVP — текущий статус разработки

**Снимок:** 2026-07-20, Europe/Moscow
**Канонический репозиторий:** `nobus-orchestrator-dev`
**Назначение:** единственная обновляемая точка передачи фактического состояния между итерациями

## Итог текущей итерации

Каноническая документация 01–10 и ADR 0001–0008 собрана в `docs/`, противоречия CURRENT/TARGET и security/operations gaps устранены. Документационный комплект получил независимый `L2/L3 PASS` и детерминированную проверку ссылок/структуры.

Временные дубли и устаревшие материалы удалены из рабочих директорий после создания трёх проверенных локальных архивов в `ОРКЕСТРАТОР\Backups\2026-07-20 Миграция документации`. Старый прототип содержал `.env`; его архив считается потенциально секретным и не подлежит публикации или добавлению в Git.

Рабочий вертикальный сценарий `Telegram → голос/текст → TaskContract → Codex CLI → L1/L2/L3 → ответ` ещё не собран. Реальный bot token, внешняя сеть, deployment и production-данные не использовались.

## Gate status

| Gate | Git / реализация | Проверка | Статус |
|---|---|---|---|
| Gate 0 — baseline | `main` / `ea5bd51` | 28 tests исторического baseline | **ACCEPTED** |
| Documentation baseline | `docs/README.md`, 01–10, ADR 0001–0008 | link/structure L1; независимые L2/L3 | **ACCEPTED; ещё не committed** |
| Gate 1 — Core contracts/policy rework | незакоммиченный diff в `main` | 68 target; 82 code tests; independent review выполняется | **DRAFT** |
| Gate 2A — Telegram ingress | commit `8478a77` в `agent/kimi-telegram` | 59 target / 87 branch full ранее приняты | **ACCEPTED; NOT INTEGRATED** |
| Gate 2B — voice preview | commit `227076d` в `agent/kimi-telegram` | 49 target / 136 branch full ранее приняты | **ACCEPTED; NOT INTEGRATED** |
| Gate 3 — Codex CLI adapter | файлов нет | не проверялся | **NOT STARTED** |
| Gate 4 — fake vertical E2E | файлов нет | не проверялся | **NOT STARTED** |
| Gate 5 — production readiness | только TARGET runbook | отсутствует persistence/deploy/monitoring/restore evidence | **BLOCKED BY DESIGN** |

## Gate 1 — что реализовано в draft

- Result/context запечатываются при `DRAFT` парой `result_revision` + `result_digest`.
- После `DRAFT` результат не меняется до явного `REWORK`.
- `REWORK` архивирует старые verification/L4 records и очищает активный цикл.
- VerificationBundle связан с tenant/task/`contract_digest`/result и хранит отдельные L1/L2/L3 records.
- Проверяющие проходят injected allowlist ролей; это ещё не аутентификация.
- WorkerEvent связан с зарегистрированными tenant/task/worker, имеет возрастающий sequence и JSON-only payload.
- Публичный ответ получает безопасный error code вместо текста внутреннего исключения.

Известные границы Gate 1: in-memory storage; `UserRequest` ещё не преобразуется единственным trusted путём в полный TaskContract; подлинность evidence и identities требует будущего boundary; TARGET approval/action binding ещё не реализован полностью.

## Точный Git-снимок

### Main worktree

- Ветка / HEAD: `main` / `ea5bd51`.
- CODEX-1 и каноническая документация находятся в рабочей копии без staging/commit.
- `.nobus-quality/cases.ndjson` содержит ранее добавленные незакоммиченные case records и должен сохраняться без перезаписи.
- Remote отсутствует; push не выполнялся.

### Kimi worktree

- Ветка / HEAD: `agent/kimi-telegram` / `227076d891e0fd2006ebfdec8337fab1c2c313e3`.
- Commits: `8478a77 feat: add safe Telegram ingress`; `227076d feat: add safe voice transcription preview`.
- Рабочая копия была чистой после commit; merge/rebase/push/remote не выполнялись.

## Автономная очередь без L4

Эти блоки разрешены локально и не требуют ручного подтверждения владельца:

1. Закрыть независимый review и локальный commit Gate 1 либо вернуть его в rework.
2. Контролируемо перенести commits Gate 2A/2B в `main`, проверить manifest и полный pytest.
3. Реализовать Codex CLI adapter только с fake process: allowlisted executable/arguments, JSONL, timeout, cancellation и safe errors.
4. Собрать fake E2E без token и сети: normalized Telegram update → preview/confirm → TaskContract → fake worker → result-bound L1/L2/L3 → Telegram response model.
5. Добавить restart/idempotency contract tests и обновить этот handoff.

## Что обязательно остановит автономную работу

Нужно явное решение владельца перед:

- вводом реального Telegram bot token или иных credentials;
- отправкой реальных сообщений, подключением webhook/polling и внешней сетью;
- установкой новой зависимости, если её нельзя обосновать и проверить локально;
- push, remote, deployment, публикацией, деньгами, удалением внешних данных или изменением доступа;
- принятием численных RPO/RTO, retention и production approval channel.

## Среда

Локальная `.venv` ссылается на отсутствующий системный Python 3.12. Проверки текущей итерации запускаются bundled Python Codex с пакетами существующей `.venv`; это диагностический обход, а не воспроизводимая production-среда. Перед release окружение нужно пересоздать из `requirements.txt` и повторить полный suite.

Единственное ожидаемое предупреждение текущих FastAPI tests — `StarletteDeprecationWarning` о будущем переходе TestClient на `httpx2`.
