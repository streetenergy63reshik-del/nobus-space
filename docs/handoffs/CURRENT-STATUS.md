# Nobus Space MVP — текущий статус разработки

**Снимок:** 2026-07-21, Europe/Moscow

**Канонический репозиторий:** `nobus-orchestrator-dev`

**Назначение:** единственная обновляемая точка передачи фактического состояния между итерациями

## Короткий итог

Каноническая документация, Core contracts/policy, Telegram ingress, bytes-only voice preview, fake-only Codex CLI boundary, local text fake E2E, trusted ingress envelope и изолированное SQLite checkpoint-хранилище приняты независимыми L1/L2/L3 и локально зафиксированы в `main`.

Компоненты ещё не образуют рабочий сетевой Telegram-оркестратор: SQLite-модуль пока не wired в runtime. Следующий автономный блок — Gate 4D: actor-bound single-use подтверждение voice preview без downloader/network. Реальные Telegram credentials, polling/webhook, Codex process, deployment и внешние записи не запускались.

## Gate status

| Gate | Реализация | Воспроизводимая проверка | Статус |
|---|---|---|---|
| Gate 0 — baseline | `ea5bd51` | исторический baseline: 28 tests | **ACCEPTED** |
| Documentation baseline | `364e6ab`, docs 01–10, ADR 0001–0008 | link/structure + независимые L2/L3 | **ACCEPTED** |
| Gate 1 — Core contracts/policy | `7b92978` | 91 target; 119 full на момент Gate; adversarial bindings/replay/state | **ACCEPTED** |
| Gate 2 — Telegram/voice | `5df4ccd` | 100 target; 252 full main; independent cancellation/replay/leakage review | **ACCEPTED** |
| Gate 3A — fake-only Codex CLI boundary | `294047c` | 33 target; 152 full на момент Gate; timeout/cancellation/protocol review | **ACCEPTED** |
| Gate 3B — live process + OS sandbox | файлов нет | real process и sandbox не проверялись | **NOT STARTED; REQUIRES SEPARATE GATE** |
| Gate 4A — local fake vertical E2E | `dfc2e66` | 10 target; 262 full; independent result/evidence/replay/leakage review | **ACCEPTED** |
| Gate 4B — trusted ingress envelope | `2afd880` | 176 target; 354 full; 20 independent regression | **ACCEPTED** |
| Gate 4C — durable SQLite checkpoints | `d775699` | 61 target; 365 full; restart/tamper/policy recovery review | **ACCEPTED; NOT WIRED** |
| Gate 5A — authenticated real Telegram boundary | файлов нет | token/network/callback authentication отсутствуют | **BLOCKED UNTIL L4** |
| Gate 5B — production readiness | только TARGET runbook | нет deploy/monitoring/restore evidence | **BLOCKED BY DESIGN** |

## Реализованные границы

### Core

- tenant/task/contract/result-bound модели;
- строгая state machine, atomic update и terminal audit lock;
- scoped idempotency, WorkerEvent replay и sequence checks;
- последовательные L1/L2/L3 с разными identities;
- L4 record для HIGH/CRITICAL и отдельный `EXECUTING` для внешнего эффекта;
- безопасные public error codes вместо текста внутренних исключений.

Runtime Core остаётся in-memory, а принятый SQLite-модуль пока изолирован. Identity/evidence пока являются утверждениями локальной server configuration, а не результатом authenticated network boundary.

### Telegram и voice

- Telegram update нормализуется без сети и SDK;
- accepted update получает self-validating `TrustedIngressEnvelope` с server-owned actor/time и точной payload binding;
- exact actor/chat binding, atomic update replay claim и opaque callback token claim;
- callback/replay stores пока in-memory;
- voice preview принимает только ограниченные bytes, очищает temp file после success/error, а при cancellation ждёт bounded drain и откладывает cleanup до фактической остановки provider;
- stream API удалён после независимого L3 resource-exhaustion finding;
- optional `faster-whisper` не установлен и не является текущей обязательной зависимостью.

### Worker

- Codex CLI adapter существует только как fake-first boundary с injected spawner;
- executable/path/permission/argv/env/JSONL/size/timeout/cancellation guards проверены;
- live subprocess implementation, реальный `codex` и OS sandbox отсутствуют;
- worker ещё не связан с Core attempt/lease/WorkerEvent.

## Git-снимок

### Main worktree

- Ветка: `main`.
- Последний принятый implementation commit: `d775699 feat: add durable SQLite policy checkpoints`.
- Предыдущие принятые commits: `2afd880`, `dfc2e66`, `5df4ccd`, `294047c`, `7b92978`, `364e6ab`, `ea5bd51`.
- Remote отсутствует; push не выполнялся.
- Канонические docs синхронизированы отдельным локальным docs commit после независимой проверки этого снимка.
- `.nobus-quality/cases.ndjson` содержит ранее добавленные незакоммиченные case records; файл сохраняется без перезаписи.

### Kimi worktree

- Ветка: `agent/kimi-telegram`.
- HEAD: `d0f0765 fix: harden Telegram and voice preview boundaries`.
- Рабочее дерево чистое.
- Исходные commits: `8478a77`, `227076d`; rework: `d0f0765`.
- Merge/rebase/push/remote не выполнялись; итог перенесён в `main` одним проверенным commit `5df4ccd`.

## Документация и уборка

- Единственный нормативный комплект находится в `nobus-orchestrator-dev/docs`.
- Временная директория черновой LLM-платформы удалена после создания локальной резервной копии.
- Устаревшие материалы корня `ОРКЕСТРАТОР/Code` и старый `space-nobus` удалены после архивирования.
- Архивы находятся в `ОРКЕСТРАТОР/Backups/2026-07-20 Миграция документации`.
- Архив старого прототипа потенциально содержит `.env`; его нельзя публиковать или добавлять в Git.
- Все четыре найденные одноразовые `test-temp-review-*` директории удалены после проверки точных путей; канонических файлов в них не было, совпадающих директорий в `ОРКЕСТРАТОР/Code` не осталось.

Проверенные SHA-256 резервных архивов:

| Архив | SHA-256 |
|---|---|
| архив черновой LLM-платформы до канонической миграции | `66BC6D282BDAB14777A97845030B052029D6562FAD03BD01DC0F4CCB8B03C457` |
| `Устаревшие материалы корня Code.zip` | `6AE9AEB25D5B5DB53375A56E0DAB64F8E06236A8CE3777D4E28B591DCDB9DA1B` |
| `space-nobus legacy source.zip` | `4351C6433CDE933176F0999D9E9D467A41402B4A312D827E2185BA73A09374D0` |

## Следующая автономная очередь без L4

1. Gate 4D: voice preview → actor-bound single-use confirm без downloader/network.
2. Gate 4E: SQLite safe outbox без реальной отправки в Telegram.
3. Gate 4F: runtime wiring и restart/recovery E2E.

## Обязательная остановка и L4

Автономная работа останавливается перед:

- вводом реального Telegram bot token или иных credentials;
- polling/webhook, реальными сообщениями и внешней сетью;
- live Codex/subprocess boundary и расширением разрешений;
- установкой новой зависимости без отдельного обоснования и проверки;
- push, remote, deployment, публикацией, деньгами, доступами и внешним удалением;
- утверждением production RPO/RTO, retention или approval channel.

## Среда и известные ограничения

- Текущие проверки используют bundled Python Codex с пакетами существующей `.venv`; локальная `.venv` ссылается на отсутствующий системный Python 3.12.
- В ограниченной среде `tmp_path` требует разрешённый локальный TEMP; это не runtime-дефект voice service.
- Ожидаемое предупреждение FastAPI tests: `StarletteDeprecationWarning` о будущем переходе TestClient на `httpx2`.
- Перед release окружение нужно создать заново из `requirements.txt`, выполнить полный suite, dependency audit и restore drill.
