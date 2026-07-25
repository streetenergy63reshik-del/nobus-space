# Nobus Space Telegram Orchestrator — CURRENT STATUS

**Дата:** 2026-07-25
**Runtime feature commit:** `e9007e9`
**Статус:** PRODUCT MVP-1 PUBLISHED — LOCAL OWNER RUNTIME
**Remote/push:** запрещены

## Что входит в кандидат

| Контур | Текущее состояние |
|---|---|
| Telegram owner binding, polling, queue, outbox | Durable SQLite, CAS lease, restart recovery |
| Codex CLI | `gpt-5.6-sol`, high reasoning, Fast, answer/research/patch profiles |
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

- Полный L1/L2 regression: `1062 passed, 2 skipped, 1 warning`.
- Calendar/Tasks/Drive read-only API health: PASS; OAuth ready, содержимое
  объектов и секреты не выводились.
- Live web-research L3: PASS; production adapter вернул пять прямых источников.
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
- Main и локальная live-ветка синхронизированы на `e9007e9`; remote/push не
  выполнялись.
- Startup Codex probe and cached Whisper warmup completed before Telegram polling.
- Runtime health: `PASS`; all four canonical SQLite databases are valid.
- Verified pre-release four-database backup:
  `ОРКЕСТРАТОР/Backups/2026-07-25 pre-release e9007e9`.
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
- Google MCP transport может деградировать независимо от API; штатный локальный
  read-only health check является разрешённым fallback.
