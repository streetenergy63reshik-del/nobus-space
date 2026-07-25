# Nobus Space Telegram Orchestrator — CURRENT STATUS

**Дата:** 2026-07-25
**Runtime feature commit:** `33b35f7`
**Live release commit:** `bec5f47`
**Статус:** PERSISTENT MOBILE CODEX — PUBLISHED LOCALLY
**Remote/push:** запрещены

## Релиз 25 июля 2026

- Production worker переведён с одноразового `codex exec --json/ephemeral` на
  официальный persistent `openai-codex` SDK/app-server `0.144.4`.
- Модель: `gpt-5.6-sol`, reasoning high, Fast. Личный чат и каждая Telegram-тема
  получают отдельный resumable thread.
- SDK-turn read-only; запись остаётся в application effects со
  snapshot/diff/atomic/CAS. Общая owner-команда не разрешает удаление файла.
- Deadline задачи — 10 800 секунд, ceiling — 14 400; polling и durable queue
  не блокируются длительным turn. Interrupt/close bounded до 15 секунд.
- Voice draft теперь полностью durable и восстанавливается после crash/restart.
- Google Tasks читает все tasklists и страницы, включая assigned tasks.
  Retry разрешён только safe reads; mutation transport-retry отключён.
- Business Notes binding v2 готов к точному owner marker; исторический импорт
  Telegram не выполняется.
- Portability исправлена: runtime layout больше не зависит от `parents[n]`.
- L1 в основном worktree: `1088 passed, 2 skipped, 1 warning`.
- L2 clean detached worktree: `1088 passed, 2 skipped, 1 warning`; `pip check`
  и `compileall` — PASS.
- L3 fault injection: `208 passed, 2 skipped, 880 deselected, 1 warning`.
- Внешнее AI-review полного дерева не выполнялось: protective egress boundary
  заблокировал передачу незакоммиченного кода без отдельного разрешения.
- Live publication и Google `NOBUS-SMOKE` завершены после документационного
  commit и свежего проверенного backup. Business Notes ожидает точный owner
  marker `#NOBUS-BIND-NOTES` в разрешённой группе.

## Что входит в релиз

| Контур | Текущее состояние |
|---|---|
| Telegram owner binding, polling, queue, outbox | Durable SQLite, CAS lease, restart recovery |
| Codex SDK/app-server | persistent `gpt-5.6-sol`, high reasoning, Fast; thread per chat/topic/profile |
| Длительные задачи | deadline 10 800 секунд; polling не блокируется worker |
| Параллельность | 2 worker; bounded durable queue и восстановление после restart |
| Голос | local faster-whisper, Russian profile, startup warmup, preview/cancel |
| Product UX | обычный текст = задача; технические ID скрыты; одна progress-card |
| Web research | отдельный read-only web-search профиль с проверяемыми ссылками |
| Local files | поиск/Telegram delivery; bounded analysis text/HTML/JSON/CSV/Word/Excel |
| Documents | Word/Excel/PDF/HTML в owner workspace; overwrite только со snapshot |
| Google | Calendar/Tasks/Drive natural commands; delete всегда action-bound L4 |
| Business Notes | encrypted tenant/chat/topic index; private local summaries/tasks |
| Context | Nobus Memory progressive retrieval: scoped 3–7 notes, client isolation, explicit Inbox writes |
| Autostart/ops | Windows Task Scheduler, health, backup, restore и rollback scripts |

## Авторизация

- Точный owner text выполняет обратимое действие без второй кнопки.
- Подтверждённая voice-транскрипция имеет ту же силу.
- Удаление, публикация, деньги, права доступа, push/deploy и применение code patch
  всегда требуют отдельного action-bound L4.
- `C:\Хранилище\WORK` вне scope. Remote и push отключены.

## Проверки текущей итерации

- Полный L1/L2 regression: `1088 passed, 2 skipped, 1 warning`.
- Calendar/Tasks/Drive read-only API health: PASS; OAuth ready, содержимое
  объектов и секреты не выводились.
- Google Tasks all-lists L3: 21 список прочитан с полной пагинацией; на неделю
  20–26 июля независимо подтверждены 36 незавершённых задач в 12 списках;
  production-контур вернул те же 36.
- Live bounded web-research L3: PASS; `gpt-5.6-sol/high/Fast` завершил четыре
  web-search и вернул структурированный результат на 7964 символа. Durable outbox
  и Telegram chunk-delivery проверены для длинного ответа.
- Natural owner-file L3: PASS; запрос без расширения выбрал точный документ
  среди двух похожих имён, не читая и не выводя его содержимое.
- Nobus Memory product/boundary L2: `117 passed`; real-vault L3: PASS (5 scoped notes, only the explicitly named client card, no network/process imports).
- Product/security targeted: `100 passed`; overwrite/restore targeted:
  `38 passed`; Codex CLI: `71 passed`.
- `compileall`: PASS; `pip check`: PASS; `git diff --check`: PASS
  (только уведомления LF→CRLF).
- Независимый L2: ACCEPT, P0/P1 отсутствуют.
- Independent final L3: ACCEPT; P0/P1/P2 absent in the accepted reliability scope.
- Owner-file reliability/security focused: 48 passed; final full suite: 1049 passed, 2 skipped, 1 warning.

## Live publication evidence

- Windows Task Scheduler: `NobusSpaceBot` — `Running`; supervised Python process
  tree is active.
- Main и локальная live-ветка синхронизированы на `bec5f47`; remote/push не
  выполнялись.
- Startup Codex probe and cached Whisper warmup завершились до Telegram polling:
  активный polling lease подтверждён после запуска.
- Runtime health: `PASS`; all four canonical SQLite databases are valid.
- Calendar/Tasks `NOBUS-SMOKE` create/update/delete: PASS; созданные этой
  проверкой объекты удалены. Google Drive read/search: PASS.
- Verified pre-release four-database backup:
  `ОРКЕСТРАТОР/Backups/2026-07-25-pre-mobile-codex-runtime-release-bec5f47`.
- Telegram polling checkpoint advanced after restart.
- Nobus Memory live retrieval: PASS; Inbox excluded until curation; vault docs commit `4a8d268`.
- Pre-memory runtime backup: `ОРКЕСТРАТОР/Backups/2026-07-25-pre-nobus-memory`.
- Verified pre-release backup:
  `ОРКЕСТРАТОР/Backups/2026-07-25-pre-product-mvp1`.
- Verified final four-database backup:
  `ОРКЕСТРАТОР/Backups/2026-07-25-product-mvp1-final`.
- Disposable restore drill: `PASS`; every restored database passed SQLite
  `quick_check`.
- Forced-process-stop recovery: `PASS`; the durable polling lease prevented a
  duplicate consumer and the runner started normally after its 240-second TTL.
- No remote, push or external repository publication was performed.

## Остаточные границы MVP-1

- PDF можно получить вложением, но его текст не разбирается без отдельного
  проверенного parser dependency.
- Business Notes обрабатывают новые сообщения после привязки чата; историческая
  выгрузка Telegram API не обещается.
- Это owner-bound локальный продукт, а не внешний multi-user SaaS.
- Удаление пользовательских файлов не разрешено этим релизом.
- Внешний restore отдельного owner artifact не опубликован: внутренний
  snapshot/CAS primitive проверен, но внешний вызов требует будущей durable
  one-shot capability, связанной с owner, путём и digest.
- Для естественной отправки файла MVP-1 поддерживает точные owner-команды
  `пришли/отправь/направь/дай мне файл|документ ...`; составная команда
  «пришли и затем проанализируй» намеренно уходит в обычный task pipeline.
- Delivery Telegram остаётся at-least-once на узком crash-окне внешнего
  `sendDocument`.
- Длинный verified answer доставляется несколькими Telegram-сообщениями. В узком
  crash-окне между частичной внешней доставкой и локальным receipt возможен
  повтор уже отправленной части; потеря полного durable результата не допускается.
- Google MCP transport может деградировать независимо от API; штатный локальный
  read-only health check является разрешённым fallback.
