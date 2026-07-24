# Orchestrator v2 — safe owner and research boundary

## Итерация 2026-07-24: безопасная owner library boundary

- Реальный native-Windows probe опроверг безопасность прямого owner-read: permission profile блокировал запись, но shell мог читать соседний каталог и deny-файл. Прямой filesystem scope LLM отвергнут.
- Owner library реализована как trusted server-side bounded path index/file-transfer: обычные ответы не получают owner permission автоматически; answer, startup probe и explicit owner index работают tool-less; public research получает только model inference и строго валидированные web-search events, без shell/local-file/apps/MCP. Owner root не попадает в CLI argv или prompt, содержимое не пересылается; анализ содержимого требует отдельного data-handling gate.
- Worktree остаётся единственной областью diff/apply. `C:\Хранилище\WORK` не входит в owner root.
- Изолированный OpenAI/Codex probe использовал только синтетические файлы в `C:\tmp`: разрешённый sentinel прочитан и запись заблокирована, но соседний и deny-файл также оказались читаемыми. Поэтому direct-read дизайн отвергнут.
- Реальные документы, секреты и бизнес-данные в probe не читались. Новая ревизия ещё не опубликована в live и ожидает общий L1/L2/L3 release cycle.

**Status:** ACCEPTED LOCAL RC — L1/L2/L3 PASS; live unchanged.

**Evidence:** 993 passed, 2 skipped, 1 known warning; targeted boundary/product suite 162 passed; Windows/web regression 35 passed; independent L2 focused 12 passed; independent L2/L3 ACCEPT with no open P0/P1/P2; `pip check`, `compileall` and `git diff --check` PASS.

---

# Orchestrator v2 — voice quality hardening

**Status:** ACCEPTED LOCAL RC — L1/L2/L3 PASS; live unchanged.

**Evidence:** 975 passed, 2 skipped, 1 known warning; `pip check`, `compileall` and `git diff --check` PASS; real cached CPU encoder warmup PASS; independent L2/L3 ACCEPT with no open P0/P1/P2.

- Exact owner voice already executes reversible commands without a second button;
  deletion and irreversible effects still require action-bound L4.
- Local `base/int8` remains the only cached model. The candidate profile uses
  Russian, beam 8, patience 1.2, VAD, cross-segment context and separate Nobus
  context/hotwords.
- One-off local Russian TTS observation retained “на завтра”, which the previous
  profile dropped; candidate decoding was about 0.6 seconds slower on that
  10-second sample. This is not a reusable accuracy benchmark.
- RTX 3050 Ti model load alone passed, but real inference exposed missing
  `cublas64_12.dll`; v2 startup now proves an in-memory encoder inference and
  remains on CPU instead of publishing a false GPU-ready state.
- A larger local/off-device speech model still requires a separately allowed
  model source or existing OpenAI speech credential; neither is assumed.

---

# Nobus Space Orchestrator v2 — owner command and Calendar RC

**Status:** ACCEPTED LOCAL RC — L1/L2/L3 PASS; live not published.
**Commits:** `4861439`, `9447832`.
**Evidence:** 973 passed, 2 skipped, 1 known warning; Calendar API read-only smoke
PASS; Google token contents were not logged or copied; `pip check` PASS;
`git diff --check` PASS.

Implemented:

- exact owner text command and locally transcribed voice command have equal
  authority for reversible allowlisted actions; no second confirmation button;
- local Whisper `base/int8` uses explicit Russian, beam 5, VAD, disabled
  cross-segment context and Nobus/business hotwords; startup warmup remains local;
- Google Calendar `LIST`, `CREATE` and `UPDATE` execute immediately from natural
  text or voice intent;
- Calendar `DELETE` resolves exactly one event and requires a separate
  tenant/user/chat/event-bound one-shot owner button;
- create uses deterministic Google event ID; same idempotency key with another
  payload is rejected;
- exact `/document`, `/download` and allowlisted `/network` owner commands execute
  without a second button; Telegram delivery has three bounded attempts;
- normal Codex execution deadline remains 10 800 seconds (3 hours); the
  120-second boundary is only the tool-free Calendar intent parser;
- `/calendar` is prepared for Bot Menu but has not been externally published.

Additional v2 blocks in the current local branch:

- Google Tasks and Drive adapters are implemented and independently accepted in commit `4a73145`;
- Business Notes v2 binding, encrypted topic index, local summaries/task extraction and four-database backup/restore are implemented; L1 is `973 passed, 2 skipped`, and independent L2/L3 are `ACCEPT` with no open P0/P1/P2;
- larger/off-device speech model evaluation remains pending;
- v2 live activation, Business Notes group binding, owner smoke and final crash/restart/rollback drill remain pending.

The accepted live runner remains on the previous revision until the final
release preflight completes. Remote and push remain disabled.

---

# Queue 1/2 reliability hotfix — voice recovery and runner continuity

**Status:** ACCEPTED LOCAL RC — L1/L2/L3 PASS; exact owner L4 live release pending.
**Evidence:** 893 passed, 2 skipped, 1 known warning; independent Queue 1/2
reproduction 84 passed; restart/retention probe PASS; P0/P1/P2 = 0. Compileall,
pip check, PowerShell parse, documentation links, diff-check, secret-pattern scan
and quality-memory validation PASS.

- Root cause локального owner smoke: voice TaskContract был связан с исходным
  voice envelope, но durable job ошибочно сохранял callback envelope. Строгий
  `recover_prepared` корректно отклонял несовпадение после трёх claims.
- Confirmation binding теперь DPAPI-durable хранит исходный envelope. Durable job
  раздельно хранит recovery envelope и action/UI envelope; Core guards не ослаблены.
  UX TTL кнопки отделён от bounded recovery-retention: после истечения действие не
  запускается, но доказанная отмена Core может безопасно повториться после restart.
- Exhausted recovery больше не исчезает молча: Task terminalization/outbox
  выполняются при валидном binding, иначе одна progress-card превращается в
  безопасную финальную ошибку. `/status` показывает dead-letter count.
- Одна карточка прогресса обновляется по безопасным стадиям Core и heartbeat
  каждые 30 секунд, затем удаляется после результата. Hidden reasoning, prompt,
  пути, секреты и технические IDs не показываются.
- Windows Task Scheduler runner/health явно разрешены при питании от батареи;
  execution deadline Gate 5A.4 остаётся 10 800 секунд (3 часа), lease 60 секунд
  продлевается отдельно и не обрезает долгую задачу.
- Локальный L1: 893 passed, 2 skipped, 1 known warning. Целевой Queue 1/2
  regression-suite: 69 passed. Compileall, pip check, PowerShell parse,
  documentation links, diff-check и quality-memory validation также прошли.
- Исправлены замечания первого независимого ревью: durable confirmation теперь
  удаляется только после доказанной отмены Core, а восстановление effect требует
  точной callback/envelope, tenant и deterministic task-id binding.
- Повторное независимое L2/L3: ACCEPT, P0/P1/P2 отсутствуют. Temp-DB probe
  воспроизвёл 3 transient cancel failures → restart → 1 successful cancel →
  terminal Core proof → capability deletion; retention upper bound также PASS.
- Live worktree остаётся clean на `0856603`; Scheduled Task сейчас `Ready`, не
  запущена. Публикация и reconciliation одной старой failed voice-задачи требуют
  exact owner L4 на новый commit hash.

---

# QUEUE-1-2-2026-07-24 — release candidate before live L4

**Status:** ACCEPTED LOCAL RC — L1/L2/L3 PASS; exact owner L4 live release pending.
**Verification:** 887 passed, 2 skipped, 1 known warning; compileall, pip check,
PowerShell parse, quality-memory validation and diff-check PASS. Independent L2 and
L3: ACCEPT, P0/P1/P2 absent. Release preflight also fixed and independently accepted
the production wiring invariant: all three canonical runtime databases share
`ROOT/.runtime`, matching backup, health and restore.
**Live state:** runner, Task Scheduler, workspace and live branch are intentionally not
updated by this release cycle; live remains clean at `74b182a`.

The active semantics are defined by
`docs/adr/0011-durable-owner-effects-and-web-profiles.md` and supersede contradictory
historical restart/process-memory notes later in this handoff.

Implemented rework:

- concrete `/research` argv is wired into the production asyncio process allowlist;
- operational CLIs run directly from the repository; Telegram profile publication
  requires explicit `--apply`;
- exact HTTPS Git destination and allowlisted inert local config are approval-bound; credentials, proxy, headers, includes and URL rewrites are rejected;
- pip is isolated from config/environment, binds exact PyPI index, rejects nested/constraint/editable/local/direct inputs and requires hashed binary distributions;
- effect capability lifetime is seven days; durable delivery receipt prevents replay
  after local delivery commit;
- a job gets at most three durable claims, then moves to a non-blocking dead letter;
- health/backup/restore validate exact DDL fingerprints and all application digests; dead letters are DEGRADED operator alerts, not restart signals;
- restore staging, rollback and replacement use fsync/write-through;
- runner mutex is cross-session; Task Scheduler alone performs up to ten bounded liveness restarts, while health never restarts persistent degraded state;
- owner artifact write revalidates parent identity immediately before replacement.

Residual accepted-for-review limitation: `sendDocument` can duplicate once if Telegram
accepted the upload and the process crashed before persisting its delivery receipt.

The earlier reviewer incident remains recorded: a profile script was accidentally run
with `--help` before it required `--apply`, so Queue-2 menu commands may already be
visible in Telegram. No compensating external write is performed without a new L4.

---

# Nobus Space MVP — текущий статус разработки

## Iteration 2026-07-24: Windows autostart and owner document delivery

- Owner L4 activated clean live revision `ffee156`.
- Windows Task Scheduler task `NobusSpaceBot` is installed for current-user logon. It uses interactive limited privileges, `StartWhenAvailable`, ten one-minute restart attempts, unlimited execution time, and ignored parallel instances.
- The scheduled task launches the canonical repository runner and writes bounded local logs under the Git-ignored live `.runtime/logs` directory. Scheduler execution and the expected Python wrapper-child process tree are running.
- Main revision `670ce88` adds owner-bound local document delivery through Telegram `sendDocument`. Supported initial types are `.docx`, `.htm`, `.html`, `.pdf`, and `.xlsx`, with a 50 MiB ceiling.
- Selection reuses the bounded 50,000-entry/8-result sensitive-name-filtered index. The content adapter rejects linked roots, traversal, symlinks and junctions, binds validation to the opened OS handle before reading, and checks stable file identity before returning bytes.
- Product routing supports explicit `/file <name-or-relative-path>` and only the exact natural form `пришли/отправь мне файл/документ <name>.<allowed-extension>`. Ambiguous instructions remain ordinary tasks.
- L1: `796 passed, 2 skipped, 1 known warning`; target adversarial sets: `156 passed` locally and `148 passed` independently. L2/L3: `ACCEPT`, no P0/P1/P2.
- Owner-only production smoke sent one known non-secret HTML successfully (`message_id=165`, `74231` bytes). Token, chat ID, absolute path and content were not logged.
- Exact owner L4 activated clean live revision `74b182a`, published `/file` in Bot Menu, passed the startup Codex probe and offline Whisper warmup, and acquired fresh polling lease revision `6868`.
- Product-route owner smoke `/file` sent the known non-secret HTML successfully (`message_id=167`, `74231` bytes). Scheduled Task `NobusSpaceBot` is running with the expected Python wrapper-child process chain.
- Google Drive delivery is not part of this revision. Ten one-minute restart attempts are configured; a destructive crash/reboot restart drill remains independently unverified.


## Итерация 2026-07-23: owner library и callback cleanup

Live runner обновлён до `8574f22`: startup Sol/high/Fast probe, локальный Whisper warmup и свежий polling lease прошли; callback cleanup активирован. Owner smoke выявил P1: передача server root в prompt не даёт Codex CLI фактического внешнего filesystem scope, поэтому прямой owner-library read признан `REWORK`.

Новая локальная ревизия в `main` заменяет прямой CLI access безопасным path-only index:

- trusted-ingress content digest валидного Telegram callback включает source `message_id`;
- после надёжной постановки действия `answerCallbackQuery` и `deleteMessage` выполняются параллельно; live-очередь не ждёт завершения Codex;
- ошибка `deleteMessage` не блокирует и не теряет подтверждённую задачу;
- owner-bound Gate 5A.4 получает отдельное `owner.library.read` для `C:\Хранилище\АГЕНТ`;
- permission fail-closed без server root и несовместим с `repo.write`;
- только при явном запросе поиска index отбирает до 8 совпадений в пределах 50 000 entries и передаёт Codex только относительные пути;
- содержимое, абсолютный owner root, hidden/control/sensitive names, symlink и junction в prompt не попадают; path scan входит в deadline;
- worktree остаётся единственной областью diff/apply/commit, web и MCP выключены;
- фактический HTML найден по адресу `PROстранство\Browser-worker MVP-1\Browser-agent MVP-1 — актуализированная дорожная карта.html` относительно owner root;
- Telegram attachment/sendDocument не реализован: доступен поиск и возврат относительного пути; чтение содержимого owner-library отложено до изолированного content adapter.

Текущий rework: owner target `66 passed`, full suite `775 passed, 2 skipped, 1 warning`; exact path-only smoke нашёл требуемый HTML первым совпадением. Cooperative timeout/cancel завершает scan thread; generic status не запускает scan, короткие `ТЗ`/`MVP`/`ИИ` находятся. Независимые L2/L3: `ACCEPT`, P0/P1/P2 нет. Live runner остаётся на `8574f22`; path-index revision ещё не активирована и потребует нового точного L4.


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
- точная локально распознанная owner voice-команда сразу авторизует обратимое действие; дополнительная inline-кнопка создаётся только для удаления, patch и иных L4-эффектов;
- callback/replay/confirmation stores сохраняют action-bound L4 capability; capability имеет TTL, хранится только в виде digest и после success заменяется replay tombstone;
- voice download ограничен 10 MiB, транскрипция выполняется локальной `faster-whisper base`, temp file очищается после success/error/cancellation;
- bot profile публикует в меню `/start`, `/status`, `/limit` и `/help`; action-bound L4 показывается inline-кнопкой только когда он действительно нужен;
- `/limit` читает exact семидневный Codex rate-limit bucket без model turn и показывает только процент и время сброса; отказ не создаёт Task;
- stream API удалён после независимого L3 resource-exhaustion finding;
- `faster-whisper==1.2.1` является точной обязательной зависимостью live voice path.

### Worker

- answer и startup probe используют только `model.inference`; public research использует `model.inference + web.search`; shell, shell snapshot, apps и MCP для этих профилей выключены;
- owner path index строится trusted server-side и передаётся tool-less как bounded относительные пути без root и содержимого; LLM не получает local-file scope;
- stdout/stderr ограничены, процесс и дерево потомков завершаются при timeout/cancellation; Windows boundary использует Job Object;
- протокол принимает strict informational `answer` JSON либо exact unified diff в отдельном patch-профиле; `.git`, `.runtime`, secrets, symlink и выход за worktree запрещены;
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
- расширением tool-less answer/startup выше `model.inference`, research выше `model.inference + web.search` или выдачей LLM прямого local-file scope;
- установкой новой зависимости без отдельного обоснования и проверки;
- push, remote, deployment, публикацией, деньгами, доступами и внешним удалением;
- утверждением production RPO/RTO, retention или approval channel.

## Среда и известные ограничения

- MVP-1 воспроизведён локальной `.venv` на Python 3.12; пересоздание окружения из manifest и restore drill остаются критериями Gate 5B.
- Runner зависит от текущей desktop-сессии Windows и не имеет OS supervisor, autostart или health alert.
- Legacy voice-preview confirmation store не используется новым direct-voice flow. Patch/delete L4 capabilities сохраняются tenant-bound durable stores и восстанавливаются после restart без автоматического применения эффекта.
- Expired patch/delete L4 capabilities очищаются bounded recovery-процессом; истёкшая capability не авторизует эффект.
- Ошибки filesystem cleanup/journal fail-closed; редкий I/O failure может потребовать restart или ручного recovery.
- SQLite polling store реализован; его `state_digest` является checksum, а не MAC против субъекта с правом переписать БД и пересчитать digest.
- Live polling разрешён только одному owner binding; временная недоступность Telegram повторяется с bounded backoff.
- Telegram-контур не выполняет merge/rebase/push и не меняет `main`; принятые L4 commits остаются в `agent/telegram-live` для последующего desktop-review.
- Ожидаемое предупреждение FastAPI tests: `StarletteDeprecationWarning` о будущем переходе TestClient на `httpx2`.
