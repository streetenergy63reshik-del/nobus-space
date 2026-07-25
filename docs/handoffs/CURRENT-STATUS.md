# CURRENT STATUS — Nobus Space MVP-1

**Статус:** ACCEPTED LOCAL OWNER RUNTIME
**Актуально на:** 24 июля 2026 года
**Канонический commit:** `aa8a02e fix: make Telegram queue recovery durable`
**Ветки:** `main` и `agent/telegram-live` указывают на `aa8a02e`
**Remote/push:** отсутствуют и не выполнялись

Этот документ — единственный активный снимок фактического состояния. Старые gate-handoff
сохраняют историю проверок, но не переопределяют сведения ниже.

## 1. Что работает сейчас

### Telegram-продукт

- owner-bound бот принимает обычный текст как read-only задачу без лишнего подтверждения;
- голос скачивается с ограничением размера, локально распознаётся Faster Whisper
  `base/cpu/int8`, затем показывается один transcript с кнопками
  `Подтверждаю` / `Отмена`;
- после использования callback карточка подтверждения удаляется;
- одновременно работают два Codex worker, остальные задания ждут durable FIFO;
- задача Codex имеет deadline 10 800 секунд; абсолютный contract ceiling —
  14 400 секунд; polling lease не ограничивает время выполнения worker;
- worker использует exact profile `gpt-5.6-sol`, reasoning `high`,
  `service_tier=fast`, fast mode, read-only sandbox, без MCP;
- `/research` включает отдельный профиль публичного web search со ссылками;
- одна редактируемая карточка показывает безопасные стадии и heartbeat каждые
  30 секунд, затем удаляется после финального результата;
- обычный интерфейс не показывает UUID, event/revision, digests, локальные
  абсолютные пути, stderr или другие технические детали;
- `/status`, `/limit`, `/file`, `/research`, `/document`, `/download`,
  `/network` и `/help` опубликованы как продуктовые команды.

### Файлы и эффекты

- owner library read scope: `C:\Хранилище\АГЕНТ`;
- `/file` безопасно ищет и отправляет `.docx`, `.htm`, `.html`, `.pdf`,
  `.xlsx` размером до 50 MiB через Telegram `sendDocument`;
- создание `.docx`, `.html`, `.pdf`, `.xlsx` разрешено только внутри
  `C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\NOBUS SPACE BOT`
  и только после точного owner L4;
- `/download` загружает только публичный HTTPS-ресурс в quarantine и требует L4;
- `/network` допускает только закрытые structured-профили `git fetch` и
  hash-pinned binary-only `pip install`, также после L4;
- code patch остаётся без эффекта до показа exact diff и owner L4; merge, rebase,
  push и подключение remote запрещены.

### Надёжность и эксплуатация

- канонические runtime-БД:
  - `.runtime/task-runtime.sqlite3`;
  - `.runtime/telegram-checkpoint.sqlite3`;
  - `.runtime/telegram-state.sqlite3`;
- jobs, confirmations, encrypted payloads, progress bindings, effects, outbox,
  receipts и polling checkpoint сохраняются до Telegram ACK;
- claims используют renewable generation-bound leases; после трёх неудачных
  claims poison job становится dead letter и не блокирует последующие задачи;
- подтверждённая voice-задача хранит раздельно исходный recovery envelope и
  callback/action envelope, поэтому restart не подменяет instruction binding;
- чувствительные durable payloads защищены Windows DPAPI текущего пользователя;
- Task Scheduler task `NobusSpaceBot` запускает runtime после входа пользователя,
  не допускает параллельный экземпляр и делает до десяти повторов с интервалом
  одна минута;
- health, backup и restore проверяют exact DDL fingerprints, application digests
  и состав всех трёх БД;
- проверенный pre-release backup:
  `C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\Backups\2026-07-24-1615-pre-aa8a02e`.

## 2. Проверки релиза `aa8a02e`

- полный локальный suite: `893 passed, 2 skipped`;
- независимый L2: `ACCEPT`;
- независимый L3: `ACCEPT`;
- критические и значимые findings P0/P1/P2: отсутствуют;
- startup Codex sentinel: PASS;
- локальный Whisper warmup из существующего кэша: PASS;
- health трёх runtime-БД: PASS;
- owner-bound Telegram smoke после активации: PASS;
- старая failed voice-задача закрыта через application boundary без повторного
  исполнения инструкции.

Точные команды воспроизведения находятся в
[`../08-Runbook-эксплуатации.md`](../08-Runbook-эксплуатации.md).

## 3. Текущий статус Gate

| Gate | Результат | Статус |
|---|---|---|
| 0 | безопасный Git baseline и secret hygiene | ACCEPTED |
| 1 | Core contracts, state policy, L1–L4 | ACCEPTED |
| 2 | Telegram ingress и безопасная voice boundary | ACCEPTED |
| 3 | изолированный Codex CLI/Windows Job boundary | ACCEPTED |
| 4A–4F | trusted envelope, SQLite, voice confirm, outbox, recovery | ACCEPTED |
| 5A | owner-bound live Telegram, text/voice, Codex, `/limit`, `/file` | ACCEPTED LIVE |
| 5B / Queue 1 | autostart, health, backup/restore, durable admission | ACCEPTED LOCAL OWNER RUNTIME |
| Queue 2 | durable effects, web/network profiles, progress UI | ACCEPTED LOCAL OWNER RUNTIME |

## 4. Остаточные ограничения

Это не внешний production deployment:

1. runner работает под Windows identity владельца; отдельной service identity и
   ACL-проекции нет;
2. внешний независимый monitoring/alert channel отсутствует;
3. RPO/RTO не утверждены как production SLO;
4. `sendDocument` имеет узкое at-least-once crash-window между ответом Telegram
   API и локальной записью delivery receipt;
5. локальный SQLite/Core не является коммерческой multi-tenant платформой;
6. форматирование длинных model-ответов остаётся ограниченным Telegram-текстом;
   отдельный report renderer — TARGET.

## 5. Запланировано после MVP-1

| Возможность | Статус |
|---|---|
| чтение тем группы «Заметки бизнеса», резюме и списки задач | TARGET |
| Google Drive read/send, Calendar и Tasks | TARGET; OAuth и внешняя запись требуют отдельных L4 |
| генерация встреч/задач из резюме | TARGET; каждое действие подтверждается |
| развитие специализированных субагентов | TARGET |
| отдельная OS identity/ACL и внешний deployment | TARGET production hardening |
| внешний мониторинг, утверждённые RPO/RTO, регулярный restore drill | TARGET production hardening |

## 6. История проблем

Консолидированный реестр причин, исправлений, проверок и остаточных рисков:
[`MVP-1-ISSUES.md`](MVP-1-ISSUES.md).
