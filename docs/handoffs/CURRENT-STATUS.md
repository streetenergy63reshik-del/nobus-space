# Nobus Space MVP — текущий статус разработки

**Снимок:** 2026-07-23, Europe/Moscow

**Канонический репозиторий:** `nobus-orchestrator-dev`

**Назначение:** единственная обновляемая точка передачи фактического состояния между итерациями

## Обновление 2026-07-23 — недельный лимит Codex (ACCEPTED LIVE)

В main commit `4ab837c` добавлена продуктовая команда `/limit` и пункт `Лимит` в Bot Menu. Команда выполняет отдельный bounded read-only запрос `account/rateLimits/read` через официальный Codex app-server, выбирает exact `codex` window длительностью 10 080 минут и показывает владельцу использованный/оставшийся процент и время сброса по Москве. Model turn, tools, web и MCP не запускаются; абсолютное число токенов OpenAI не сообщает.

Fail-closed границы: exact argv allowlist синхронизирован в adapter, Windows Job launcher и helper; JSONL ограничен по числу сообщений и размеру; дублирующиеся JSON keys, неверный bucket/window/type/процент и provider error отвергаются; timeout 15 секунд; process tree завершается при success, error и cancellation. Ошибка даёт одно безопасное сообщение и не создаёт Task. Startup-order сохранён: limit provider создаётся только после успешных Codex worker probe и локального Whisper warmup.

Проверки: `56 passed` target; `754 passed, 2 skipped, 1 known warning` full; `pip check` и `compileall` — PASS; production-path smoke через тот же sanitized environment и Windows Job — PASS (`15%` использовано, `85%` осталось, reset `2026-07-30 10:00 MSK` на момент проверки). По exact owner L4 Bot Menu опубликован, live-ветка fast-forward обновлена до `08e8917`, startup Sol/high/Fast probe и локальный Whisper warmup прошли до получения новой generation-bound polling lease; runner активен.

## Обновление 2026-07-23 — concurrent Telegram execution (ACCEPTED LIVE)

В main реализован ADR 0009: production CLI profile `gpt-5.6-sol` + `high` reasoning + Fast mode; Gate 5A.4 execution deadline 10 800 секунд при абсолютном ceiling 14 400 секунд; Telegram polling отделён от worker execution. Два read-only workers выполняют независимые задачи параллельно. Admission допускает 32 ожидающих drafts в общей очереди maxsize 40 с резервом для L4. Overflow и controlled close считают job завершённым только после exact durable terminal proof; persistent failure запрещает polling ACK или clean close. Exact owner-approved patch сохраняет эксклюзивный Git/L2/L3/apply/commit boundary.

Локальный regression подтверждает быстрый приём пяти задач: две активны, три находятся в очереди; `/status` показывает оба счётчика. False `REJECTED` без SQLite-write, persistent overflow, active cancellation, concurrent close и реальные Gate wrappers проверены adversarial tests. Полный suite: `745 passed, 2 skipped, 1 known warning`; независимое L2/L3: `ACCEPT`, P0/P1/P2 отсутствуют. Очередь process-memory и не обещает crash replay raw instruction. По exact owner L4 residual crash-risk принят; live runner `08e8917` прошёл startup probe, warmup и получил свежую polling lease. Owner queue smoke остаётся `PENDING`.

## Обновление 2026-07-23 — callback/worker timeout hardening

Owner smoke воспроизвёл последовательную задержку: `answerCallbackQuery` занял около 60 секунд, затем worker работал ровно 120 секунд и завершился `worker_timeout`; безопасная ошибка была доставлена через durable outbox примерно через три минуты после нажатия.

Исправление `496e891` ограничивает optional callback acknowledgement двумя секундами и фиксирует Telegram Codex worker на `gpt-5.6-terra` с `model_reasoning_effort=medium`. Capability остаётся одноразовой; timeout/API failure acknowledgement не задерживает worker, а cancellation не поглощается. Exact argv синхронизирован с Windows Job helper и сохраняет read-only sandbox, web disabled, empty MCP и allowlisted environment.

Проверки: `99 passed` target; `731 passed, 2 skipped, 1 warning` full; независимое L2/L3 — `ACCEPT`, P0/P1/P2 отсутствуют. Текущий live runner остаётся на `e5405f7`; `496e891` проверен и закоммичен, но потребует нового owner L4, startup probe и перезапуска.

## Обновление 2026-07-23 — voice latency hardening

По безопасным серверным меткам текстовая задача заняла около 10 секунд. Первый voice preview появился примерно через 82 секунды; после подтверждения callback был принят, но Codex worker выполнялся ещё около 68 секунд без видимого промежуточного отклика. Это разделило проблему на первый запуск локальной voice-модели и продуктовую обратную связь callback, а не общий отказ Telegram polling.

Исправление `e5405f7` прогревает `faster-whisper base/int8` из существующего локального cache с `local_files_only=True` до начала polling и добавляет только ephemeral callback toast `Обрабатываю…`, без нового сообщения в чат. Порядок запуска fail-closed: production Codex probe → local Whisper warmup → control plane → polling/announcement.

Проверки: `107 passed` target; `730 passed, 2 skipped, 1 warning` full; offline production warmup `1.693 s`; независимое L2/L3 — `ACCEPT`, P0/P1/P2 отсутствуют. После owner L4 live-ветка fast-forward обновлена до `e5405f7`; startup probe и local-only Whisper warmup завершились до polling, а свежая generation-bound lease подтверждает активный runner.

## Обновление 2026-07-23 — product execution hardening

Исправление `27f9cd9` завершило продуктовый контур выполнения задач: рабочий Codex CLI выбирается самопроверкой, информационный ответ и code patch разделены строгим JSON-протоколом, а проверенный ответ доставляется через существующий tamper-evident SQLite outbox до ACK.

Для информационных задач введён терминальный статус `ANSWERED`; для изменений кода сохранён полный L4-путь до `COMPLETED`. Тип результата (`answer`/`patch`) фиксируется в audit trail и проверяется одновременно policy, StateManager и SQLite projection.

Продуктовый Telegram-интерфейс больше не показывает UUID задач, Event/Revision, capability-коды и другие служебные идентификаторы. Обычный текст сразу берётся в read-only работу; голос сначала транскрибируется и подтверждается кнопками; patch показывается с кнопками применения/отклонения.

Независимое L2/L3 review: `ACCEPT`, P0/P1/P2 отсутствуют. Reliability-релиз добавляет fail-fast startup probe того же production worker, сохраняет безопасные причины отказов и убирает служебные подтверждения из обычного продуктового диалога. Проверки: `127` target; `190 passed, 1 skipped` adversarial; `727 passed, 2 skipped, 1 warning` full. Одноразовый изолированный probe подтвердил CLI/auth/network/config. Live runner `36c17e4` затем прошёл встроенный startup probe, получил новую generation-bound polling lease и остаётся активным.
## Короткий итог

MVP-1 реализован и live-активирован до `e5405f7`: owner-bound Telegram polling соединён с реальным Codex CLI в режиме `read-only`, безопасным exact-diff parser, последовательными L1/L2/L3, отдельным L4 и CAS-commit в изолированной ветке `agent/telegram-live`. Callback/worker fix `496e891` независимо принят, но ещё не активирован.

Обычное текстовое сообщение по умолчанию сразу становится задачей и создаёт только read-only черновик. Если черновик содержит изменение кода, бот показывает полный diff и кнопки `✅ Применить` / `❌ Отклонить`; без L4 рабочее дерево не изменяется.

Голосовое сообщение скачивается с ограничением размера, транскрибируется локальной `faster-whisper base` на CPU и сначала показывается владельцу с кнопками `✅ Подтверждаю` / `❌ Отмена`. Модель загружена в Git-игнорируемый runtime cache; временное аудио очищается.

Crash consistency защищена pre-apply journal, exact-path restore, `commit-tree → persisted journal → CAS update-ref` и restart reconciliation. Независимый L2/L3 verdict: `ACCEPT`; P0/P1/P2 отсутствуют. Reliability suite: `727 passed, 2 skipped, 1 warning`.

Продуктовый runner `e5405f7` активен в текущей desktop-сессии. Startup read-only OpenAI probe прошёл до начала polling; свежая SQLite lease подтверждает единственного активного потребителя. OS service/autostart, внешний deploy, monitoring и restore drill остаются отдельным Gate 5B.

## Gate status

| Gate | Реализация | Воспроизводимая проверка | Статус |
|---|---|---|---|
| Gate 0 — baseline | `ea5bd51` | исторический baseline: 28 tests | **ACCEPTED** |
| Documentation baseline | `364e6ab`, docs 01–10, ADR 0001–0008 | link/structure + независимые L2/L3 | **ACCEPTED** |
| Gate 1 — Core contracts/policy | `7b92978` | 91 target; 119 full на момент Gate; adversarial bindings/replay/state | **ACCEPTED** |
| Gate 2 — Telegram/voice | `5df4ccd` | 100 target; 252 full main; independent cancellation/replay/leakage review | **ACCEPTED** |
| Gate 3A — fake-only Codex CLI boundary | `294047c` | 33 target; 152 full на момент Gate; timeout/cancellation/protocol review | **ACCEPTED** |
| Gate 3B.1 — PRE-LIVE process adapter | `cde0bd5` | 10 target process tests; cancellation/overflow/tree-guard review | **ACCEPTED PRE-LIVE** |
| Gate 3B.2a — Windows Job substrate | `1d4029f` | 7 fake WinAPI tests; startup/ABA/cancellation/handle review | **ACCEPTED PRE-LIVE** |
| Gate 3B.2b — Windows Job live probe | `6b0f923` | 17 target; 534 full; 2 live runs; 1 independent reproduction; orphan/temp audit | **ACCEPTED; REAL CODEX EXCLUDED** |
| Gate 4A — local fake vertical E2E | `dfc2e66` | 10 target; 262 full; independent result/evidence/replay/leakage review | **ACCEPTED** |
| Gate 4B — trusted ingress envelope | `2afd880` | 176 target; 354 full; 20 independent regression | **ACCEPTED** |
| Gate 4C — durable SQLite checkpoints | `d775699` | 61 target; 365 full; restart/tamper/policy recovery review | **ACCEPTED; WIRED IN 4F** |
| Gate 4D — actor-bound voice confirmation | `438233c` | 46 target; 192 relevant; 460 full; independent replay/race/tenant review | **ACCEPTED; IN-MEMORY; WIRED IN 4F** |
| Gate 4E — durable status outbox | `afb6859` | 110 target; 414 full; independent replay/time/receipt review | **ACCEPTED; WIRED IN 4F** |
| Gate 4F — durable local runtime E2E | `a56bdf3` | 14 target; 135 relevant; 475 full; independent crash/replay/tenant/delivery review | **ACCEPTED; LOCAL FAKE** |
| Gate 5A.1 — PRE-LIVE Telegram API/polling boundary | `cde0bd5` | 24 target Telegram tests; lease/offset/leakage/limit review | **ACCEPTED PRE-LIVE** |
| Gate 5A.2a — durable polling checkpoint | `1d4029f` | 18 SQLite tests; restart/CAS/expiry/clock/tamper review | **ACCEPTED PRE-LIVE; LIVE ACTIVATED IN 5A.2b** |
| Gate 5A.2b — live owner control plane | `b17f650`, `96fa634`, `17ac081` | verified identity/binding; live poll/send; 11 retry tests; 609 full; independent retry review | **ACCEPTED LIVE TEXT CONTROL** |
| Gate 5A.3 — confirmed Telegram fake tasks | `70941d8` | 36 target; 630 full; independent review; owner live terminal `completed`; SQLite/outbox ACK evidence | **ACCEPTED LIVE FAKE E2E; LIVE CODEX EXCLUDED** |
| Gate 5A.4 — product text/voice + live Codex execution flow | `42f093a`, `08e8917` | 745 full; independent ACCEPT; owner L4 activation; current polling lease active | **ACCEPTED LIVE; OWNER QUEUE/DIFF SMOKE PENDING** |
| Gate 5A.5 — weekly Codex usage visibility | `4ab837c`, `08e8917` | 56 target; 754 full; exact 7-day bucket production smoke; owner L4 live activation | **ACCEPTED LIVE; OWNER `/limit` SMOKE PENDING** |
| Gate 5B — production readiness | только TARGET runbook | нет deploy/monitoring/restore evidence | **BLOCKED BY DESIGN** |

## Реализованные границы

### Core

- tenant/task/contract/result-bound модели;
- строгая state machine, atomic update и terminal audit lock;
- scoped idempotency, WorkerEvent replay и sequence checks;
- последовательные L1/L2/L3 с разными identities;
- L4 record для HIGH/CRITICAL и отдельный `EXECUTING` для внешнего эффекта;
- безопасные public error codes вместо текста внутренних исключений.

StateManager и PolicyStore остаются process-memory, но recovery-safe Task projection, ingress claims, WorkerEvents и status outbox сохраняются в SQLite. Worker/verifier identities и completion evidence пока являются утверждениями локальной server configuration, а не результатом отдельной authenticated execution/verification boundary; Telegram actor identity проверяется live owner boundary.

### Telegram и voice

- Telegram update нормализуется без сети и SDK;
- PRE-LIVE Bot API client владеет injected transport, запрещает ambient HTTP authority/redirect/compression и ограничивает response/download;
- polling использует concrete SQLite generation-bound lease/checkpoint: store-owned clock, expiry reclaim, exact-generation CAS, restart resume и parallel-consumer exclusion;
- accepted update получает self-validating `TrustedIngressEnvelope` с server-owned actor/time и точной payload binding;
- exact actor/chat binding, atomic update replay claim и opaque callback token claim;
- обычный текст без команды сразу становится read-only задачей; `/task` оставлен только как обратная совместимость;
- voice preview подтверждается единожды тем же tenant/actor/role/auth context/user/chat через inline-кнопки; capability имеет TTL, хранится только в виде digest и после success заменяется replay tombstone;
- callback/replay/confirmation stores остаются in-memory и после restart безопасно теряют незавершённые challenge без применения эффекта;
- voice download ограничен 10 MiB, транскрипция выполняется локальной `faster-whisper base`, temp file очищается после success/error/cancellation;
- bot profile публикует в меню `/start`, `/status`, `/limit` и `/help`; технические подтверждения скрыты за inline-кнопками;
- `/limit` читает exact семидневный Codex rate-limit bucket без model turn и показывает только процент и время сброса; отказ не создаёт Task;
- stream API удалён после независимого L3 resource-exhaustion finding;
- `faster-whisper==1.2.1` является точной обязательной зависимостью live voice path.

### Worker

- реальный Codex CLI запускается только с `repo.read` и `process.run_allowlisted`; `workspace-write`, web и MCP отсутствуют;
- stdout/stderr ограничены, процесс и дерево потомков завершаются при timeout/cancellation; Windows boundary использует Job Object;
- ответ принимается только как exact unified diff с allowlist путей; `.git`, `.runtime`, secrets, symlink и выход за worktree запрещены;
- L1 проверяет patch/apply-check, L2 применяет diff и выполняет полный suite, L3 stage/audit не создаёт commit;
- после owner-bound L4 создаются immutable approval evidence и локальный commit через `commit-tree` + CAS `update-ref`;
- merge, rebase, push, remote и изменение `main` через Telegram отсутствуют.

## Git-снимок

### Main worktree

- Ветка: `main`.
- Последний проверенный implementation commit: `4ab837c feat: report weekly Codex limit in Telegram`.
- Hardening live Codex boundary: `007640b`.
- Предыдущие live Telegram commits: `70941d8`, `17ac081`, `96fa634`, `b17f650`.
- Remote отсутствует; push не выполнялся.
- Канонические docs синхронизированы отдельным локальным docs commit после независимой проверки этого снимка.
- `.nobus-quality/cases.ndjson` содержит append-only обезличенные case records принятых и отклонённых итераций.

### Live worktree

- Ветка: `agent/telegram-live`.
- Текущий HEAD работающего runner: `08e8917`.
- Telegram может создавать локальные commits только в этой ветке после exact owner L4; merge/rebase/push отсутствуют.

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

## Оценка готовности Telegram MVP

Расчёт ведётся по фиксированным весам обязательных блоков, а не по числу файлов или тестов.

| Блок | Вес | Фактический статус | Зачтено |
|---|---:|---|---:|
| Baseline и каноническая документация | 5% | ACCEPTED | 5% |
| Core contracts, state/policy и L1–L4 | 15% | ACCEPTED | 15% |
| Authenticated Telegram ingress, owner binding и меню | 15% | ACCEPTED LIVE | 15% |
| Voice download, transcription и confirmation UX | 10% | IMPLEMENTATION ACCEPTED; OWNER SMOKE PENDING | 10% |
| SQLite checkpoints, events и status outbox | 15% | ACCEPTED LIVE | 15% |
| Read-only Codex worker и exact patch boundary | 20% | IMPLEMENTATION ACCEPTED; OWNER SMOKE PENDING | 20% |
| Crash recovery, L1–L3 и owner-bound L4 | 10% | ACCEPTED | 10% |
| Product text/voice flow в изолированной Git-ветке | 10% | IMPLEMENTATION ACCEPTED; RELIABILITY RUNNER ACTIVE; OWNER PRODUCT SMOKE PENDING | 10% |
| **Итого implementation scope** | **100%** | **реализация независимо принята** | **100%** |

Implementation scope завершён на 100%; reliability startup и polling — `PASS`. Итоговая live product acceptance остаётся `PENDING` до owner smoke обычной задачи, voice и diff/apply. Это не production-readiness: supervised startup, health alert, backup/restore drill и внешний deployment вынесены в Gate 5B.

Материалы Kimi D1–D4 сохранены только как `REWORK`-черновик в `ОРКЕСТРАТОР/Backups/2026-07-21 Kimi Web drafts`; исходная `Kimi handoffs/2026-07-21 Web tasks` удалена после проверки ZIP `ADBFAA13F435567E4221A806452331FDDF66714B56753A965A628EA6BFE2D218`. E1–E4 не архивировались, поскольку полностью заменены принятым Gate 4E.

## Следующая очередь

1. Выполнить owner smoke `/limit`, затем повторить text/voice/queue smoke и owner-approved diff/apply.
2. Gate 5B выполнять отдельно: supervised startup/autostart, health/alerting, backup/restore drill и эксплуатационный runbook. Эти действия требуют отдельной проверки риска и L4.

## Обязательная остановка и L4

Автономная работа останавливается перед:

- заменой Telegram credential, owner binding или добавлением нового адресата/чата;
- внешними сообщениями вне уже разрешённой owner-bound control-plane сессии;
- расширением разрешений Codex выше текущих `repo.read` и `process.run_allowlisted`;
- установкой новой зависимости без отдельного обоснования и проверки;
- push, remote, deployment, публикацией, деньгами, доступами и внешним удалением;
- утверждением production RPO/RTO, retention или approval channel.

## Среда и известные ограничения

- MVP-1 воспроизведён локальной `.venv` на Python 3.12; пересоздание окружения из manifest и restore drill остаются критериями Gate 5B.
- Runner зависит от текущей desktop-сессии Windows и не имеет OS supervisor, autostart или health alert.
- Voice/patch confirmation stores находятся в памяти: после restart незавершённый preview безопасно теряется и задачу требуется отправить снова.
- Expired confirmations очищаются при следующем принятом Telegram update, а не отдельным background timer.
- Ошибки filesystem cleanup/journal fail-closed; редкий I/O failure может потребовать restart или ручного recovery.
- SQLite polling store реализован; его `state_digest` является checksum, а не MAC против субъекта с правом переписать БД и пересчитать digest.
- Live polling разрешён только одному owner binding; временная недоступность Telegram повторяется с bounded backoff.
- Telegram-контур не выполняет merge/rebase/push и не меняет `main`; принятые L4 commits остаются в `agent/telegram-live` для последующего desktop-review.
- Ожидаемое предупреждение FastAPI tests: `StarletteDeprecationWarning` о будущем переходе TestClient на `httpx2`.
