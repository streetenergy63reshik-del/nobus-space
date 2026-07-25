# Nobus Space Telegram Orchestrator — CURRENT STATUS

**Дата:** 2026-07-25
**Live commit:** `98a9ca3`
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
| Context | компактный проектный контекст только для Nobus/PROстранство вопросов |
| Autostart/ops | Windows Task Scheduler, health, backup, restore и rollback scripts |

## Авторизация

- Точный owner text выполняет обратимое действие без второй кнопки.
- Подтверждённая voice-транскрипция имеет ту же силу.
- Удаление, публикация, деньги, права доступа, push/deploy и применение code patch
  всегда требуют отдельного action-bound L4.
- `C:\Хранилище\WORK` вне scope. Remote и push отключены.

## Проверки текущей итерации

- Полный L1: `1043 passed, 2 skipped, 1 warning`.
- Product/security targeted: `100 passed`; overwrite/restore targeted:
  `38 passed`; Codex CLI: `71 passed`.
- `compileall`: PASS; `pip check`: PASS; `git diff --check`: PASS
  (только уведомления LF→CRLF).
- Независимый L2: ACCEPT, P0/P1 отсутствуют.
- Independent final L3: ACCEPT; P0/P1/P2 absent in the accepted reliability scope.
- Owner-file reliability/security focused: 48 passed; final full suite: 1043 passed, 2 skipped, 1 warning.

## Live publication evidence

- Windows Task Scheduler: `NobusSpaceBot` — `Running`; supervised Python process
  tree is active.
- Startup Codex probe and cached Whisper warmup completed before Telegram polling.
- Runtime health: `PASS`; all four canonical SQLite databases are valid.
- Telegram polling checkpoint advanced after restart.
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
