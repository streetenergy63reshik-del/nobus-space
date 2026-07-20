# Nobus Space MVP — текущий статус разработки

**Снимок:** 2026-07-21, Europe/Moscow

**Канонический репозиторий:** `nobus-orchestrator-dev`

**Назначение:** единственная обновляемая точка передачи фактического состояния между итерациями

## Короткий итог

Каноническая документация, Core contracts/policy, Telegram ingress, bytes-only voice preview и fake-only Codex CLI boundary приняты независимыми L1/L2/L3 и локально зафиксированы в `main`.

Компоненты ещё не соединены в рабочий Telegram-оркестратор. Следующий автономный блок — Gate 4A: полностью локальный fake vertical E2E без токена, сети и live process. Реальные Telegram credentials, polling/webhook, Codex process, deployment и внешние записи не запускались.

## Gate status

| Gate | Реализация | Воспроизводимая проверка | Статус |
|---|---|---|---|
| Gate 0 — baseline | `ea5bd51` | исторический baseline: 28 tests | **ACCEPTED** |
| Documentation baseline | `364e6ab`, docs 01–10, ADR 0001–0008 | link/structure + независимые L2/L3 | **ACCEPTED** |
| Gate 1 — Core contracts/policy | `7b92978` | 91 target; 119 full на момент Gate; adversarial bindings/replay/state | **ACCEPTED** |
| Gate 2 — Telegram/voice | `5df4ccd` | 100 target; 252 full main; independent cancellation/replay/leakage review | **ACCEPTED** |
| Gate 3A — fake-only Codex CLI boundary | `294047c` | 33 target; 152 full на момент Gate; timeout/cancellation/protocol review | **ACCEPTED** |
| Gate 3B — live process + OS sandbox | файлов нет | real process и sandbox не проверялись | **NOT STARTED; REQUIRES SEPARATE GATE** |
| Gate 4A — local fake vertical E2E | файлов нет | Telegram → Core → fake worker ещё не связан | **NEXT** |
| Gate 4B — authenticated real Telegram boundary | файлов нет | token/network/callback authentication отсутствуют | **BLOCKED UNTIL L4** |
| Gate 5 — production readiness | только TARGET runbook | нет persistence/deploy/monitoring/restore evidence | **BLOCKED BY DESIGN** |

## Реализованные границы

### Core

- tenant/task/contract/result-bound модели;
- строгая state machine, atomic update и terminal audit lock;
- scoped idempotency, WorkerEvent replay и sequence checks;
- последовательные L1/L2/L3 с разными identities;
- L4 record для HIGH/CRITICAL и отдельный `EXECUTING` для внешнего эффекта;
- безопасные public error codes вместо текста внутренних исключений.

Core остаётся in-memory. Identity/evidence пока являются утверждениями вызывающей стороны, а не результатом authenticated boundary.

### Telegram и voice

- Telegram update нормализуется без сети и SDK;
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
- Последний принятый implementation commit: `5df4ccd feat: add hardened Telegram and voice previews`.
- Предыдущие принятые commits: `294047c`, `7b92978`, `364e6ab`, `ea5bd51`.
- Remote отсутствует; push не выполнялся.
- Канонические docs синхронизируются отдельным локальным docs commit после проверки этого снимка.
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
- В `ОРКЕСТРАТОР/Code` остаются два одноразовых `test-temp-review-*`: автоматическое удаление отклонено защитным контролем среды. Они не входят в Git и не содержат канонических файлов.

Проверенные SHA-256 резервных архивов:

| Архив | SHA-256 |
|---|---|
| архив черновой LLM-платформы до канонической миграции | `66BC6D282BDAB14777A97845030B052029D6562FAD03BD01DC0F4CCB8B03C457` |
| `Устаревшие материалы корня Code.zip` | `6AE9AEB25D5B5DB53375A56E0DAB64F8E06236A8CE3777D4E28B591DCDB9DA1B` |
| `space-nobus legacy source.zip` | `4351C6433CDE933176F0999D9E9D467A41402B4A312D827E2185BA73A09374D0` |

## Следующая автономная очередь без L4

1. Gate 4A contract adapter: trusted fake ingress → TaskContract/Task без новых прав.
2. Gate 4A local E2E: text ingress → fake Codex result → explicit fake L1/L2/L3 → safe response model.
3. Voice preview E2E на bytes fixture без сети и реального provider.
4. Restart/idempotency contract tests на сериализуемом fake store; production persistence не заявлять.
5. Обновить документацию и handoff по фактическому результату.

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
