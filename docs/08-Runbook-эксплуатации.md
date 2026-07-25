## Operational override 2026-07-25 — persistent Codex SDK candidate

Этот раздел отменяет ниже расположенные инструкции, где production worker
описан как `CodexCliAdapter`/`codex exec --json --ephemeral`.

- Release-candidate: `33b35f7`; live-ветка не считается обновлённой до отдельного
  backup/switch/smoke receipt.
- Прямые зависимости закреплены: `openai-codex==0.144.4`,
  `openai-codex-cli-bin==0.144.4`.
- App-server persistent; thread name выводится из tenant, Telegram chat/topic,
  quality profile и cwd. Технический thread id пользователю не показывается.
- Model-turn: `gpt-5.6-sol`, reasoning high, Fast, `read-only`, `deny_all`.
  Web включается только research-profile; effects применяет приложение.
- Task deadline — 10 800 секунд, ceiling — 14 400; control interrupt/close —
  15 секунд. Telegram poll/queue продолжают работу независимо от turn.
- Startup ready допускается только после SDK sentinel, Whisper warmup, четырёх
  SQLite health checks и получения polling lease.
- Google read может повторяться не более двух раз; create/update/delete
  transport-retry не имеют. Неизвестный write outcome требует reconciliation.
- Business Notes binding создаётся только точным marker
  `#NOBUS-BIND-NOTES` от server-bound owner непосредственно в группе с точным
  названием «Заметки бизнеса». Marker в личном чате с ботом не содержит
  group chat proof и намеренно только возвращает инструкцию; после marker в
  группе писать боту в личный чат «Подключи Заметки бизнеса» не требуется.
  Содержимое и идентификаторы в лог не выводятся.
- Rollback target до публикации — live commit `420c9a6` плюс свежий проверенный
  backup четырёх runtime-БД и локальной конфигурации.
## Operational override 2026-07-24 — Queue 1/2 release candidate

This section supersedes older process-memory/restart instructions below.

### Runtime rules

- Accepted jobs live in `.runtime/telegram-state.sqlite3`; queue size is 40.
- Safe read-only work gets at most three durable claims. The third failure is a dead
  letter and makes the health probe report `DEGRADED`; later FIFO items remain claimable.
- An interrupted network command is never retried blindly.
- Completed Telegram effects use a delivery receipt. `sendDocument` still has a narrow
  at-least-once crash window because Telegram exposes no idempotency key.
- Confirmation capabilities expire after seven days.

### Business Notes live binding preflight

1. Keep the operator-owned binding file outside Git and migrate it atomically to
   schema version 2.
2. Preserve exactly one `owner_private` binding and add one separate
   `business_notes` binding for the exact owner user and negative forum chat ID.
   Recalculate the proof with the local configuration helper; never paste IDs,
   proofs or note contents into Markdown or logs.
3. Make the bot an administrator of the forum or disable BotFather privacy mode,
   otherwise Telegram will not deliver ordinary topic messages. Grant only the
   permissions needed to read incoming messages and reply in topics.
4. Verify a health `PASS`, then run an owner-only smoke in a dedicated test topic:
   one text note, one voice note, `/summary` and `/tasks`. Confirm that replies
   carry the same `message_thread_id` and that no note becomes a Codex task.
5. Restart the runner and repeat `/summary`; then execute backup/restore in a
   disposable runtime copy and verify that the encrypted note survives.

Do not activate the group binding when privacy/admin delivery is unresolved.
Business-note payloads must never be printed by smoke scripts.

### Read-only checks

```powershell
.\.venv\Scripts\python.exe scripts\check_telegram_health.py
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -q --disable-warnings
```

The health command requires all four databases, exact DDL fingerprints and valid
application digests. `PASS` means healthy, `DEGRADED` means operator reconciliation
(for example a dead letter), and `FAIL` means corruption/unavailability. The health
task only records an alert; it never restarts the runner. Task Scheduler owns the
single bounded liveness contract: at most ten one-minute restart attempts.

### Backup

Stop/quiesce the runner through the shared mutex, then create a new directory:

```powershell
.\.venv\Scripts\python.exe scripts\backup_telegram_runtime.py <new-backup-directory>
```

The backup is accepted only when source and copied schemas, payloads and hashes pass.

### Restore (L4)

Restore is an external state change and requires an exact owner-bound approval:

```powershell
.\.venv\Scripts\python.exe scripts\restore_telegram_runtime.py `
  <backup-manifest.json> `
  --approval-ref telegram-owner-confirmation:sha256:<64-hex>
```

The journal, staged files and rollback copies are flushed before replacement. A startup
recovery rolls back an interrupted multi-database install.

### Telegram product profile (L4)

`--help` and a missing flag never write to Telegram. Publication is explicit:

```powershell
.\.venv\Scripts\python.exe scripts\configure_telegram_profile.py --apply
```

Do not run this command before the release candidate has independent L2/L3 `ACCEPT`.

# 08. Runbook эксплуатации

## Operational update 2026-07-24: current-user autostart

This section supersedes the older statement that the MVP has no autostart.

The owner-approved host has a Task Scheduler task named `NobusSpaceBot`. It starts after current-user logon with limited interactive privileges, ignores duplicate starts, has no execution-time limit, starts when available, continues on battery power, and is configured for up to ten retries one minute apart after failure. Its launcher is Git-ignored in the live worktree and runs the canonical repository `scripts/run_telegram_mvp1.py --serve --timeout 30 --announce`. Logs are local, bounded, and stored under live `.runtime/logs`; they must never contain credentials, raw prompts, voice content, or document content.

The task is host-local configuration, not a portable deployment artifact. After repository relocation, credential rotation, Python environment replacement, or Windows account change, an operator must revalidate the exact action, working directory, principal, startup probe, Whisper warmup, polling lease and process tree. Automatic restart settings are configured; a destructive crash/reboot drill has not yet been independently reproduced.

Revision `74b182a` is active in the live runner under exact owner L4. `/file` is published in Bot Menu; startup Codex probe, offline Whisper warmup and fresh polling lease revision `6868` passed before service readiness. A product-route owner smoke sent one known non-secret HTML successfully. The adapter supports only `.docx`, `.htm`, `.html`, `.pdf`, and `.xlsx` up to 50 MiB. It never sends hidden/sensitive-name matches, absolute paths, linked paths, or content outside the configured owner root. Google Drive read/download and owner-bound Google Tasks actions are present in the v2 local RC. Business Notes adds the fourth encrypted runtime database; its live group binding remains pending.


**Статус документа:** CANONICAL
**Состояние реализации:** CURRENT Queue 1/2 local release candidate / TARGET production
**Дата актуализации:** 24 июля 2026

## CURRENT и TARGET

**CURRENT:** owner-bound Telegram runtime использует durable SQLite jobs,
confirmations, progress bindings, polling checkpoint и status outbox. Task Scheduler
является единственным liveness supervisor и выполняет максимум десять перезапусков.
Отдельная health-задача только фиксирует `DEGRADED`/`FAIL` и не перезапускает runner.
Backup/restore проверяют exact DDL и application digests. Text/voice read-only work,
public web research и owner-L4 effects определены ADR 0011.

**TARGET:** отдельная production OS identity/ACL, внешний deployment pipeline,
независимый канал alerts и утверждённые RPO/RTO. Эти production-hardening пункты не
являются обещаниями текущего локального MVP.

## 1. Среды

| Среда | Данные | Внешние действия | Назначение |
|---|---|---|---|
| `development` | синтетические/обезличенные | только fake | разработка и unit tests |
| `staging` | синтетические либо специально разрешённые | sandbox провайдера | интеграционные, E2E, миграции и rollback |
| `production` | разрешённые tenant data | только через L4 boundary | рабочая эксплуатация |

Среды имеют отдельные базы, хранилища, bot tokens, service identities, encryption keys и allowlists. Перенос production-данных в development запрещён. Конфигурация валидируется на старте и fail-closed при неизвестном или недопустимом значении.

Локальный `.env` допустим только для development и не считается защищённым хранилищем секретов. Production secrets должны находиться в специализированном secret store с аудитом доступа, ротацией и минимальными правами.

## 2. Определение релиза

`git push` лишь передаёт commit и **не является deployment**. Релиз — воспроизводимый набор:

- точный commit и immutable artifact digest;
- lock/manifest прямых зависимостей;
- версии schema, policy, model, prompt и tools;
- миграции и проверенный план rollback;
- L1/L2/L3 verification bundle;
- changelog, известные ограничения и ответственный;
- L4 на конкретный production deployment.

### Preflight

Перед staging и production необходимо проверить:

1. рабочее дерево чистое, артефакт собран повторяемо;
2. unit, contract, integration, adversarial и E2E tests прошли;
3. нет секретов, запрещённых зависимостей и уязвимостей критичного уровня;
4. миграция проверена на копии схемы, rollback либо forward-fix воспроизведён;
5. backup и последний restore drill действительны для изменяемых компонентов;
6. observability, alert routes и kill switch работают;
7. capacity и cost limits заданы;
8. L1–L3 относятся к тому же artifact digest.

### Deployment

1. Получить action-bound L4 с TTL на конкретную среду и artifact digest.
2. Включить maintenance/read-only режим, если этого требует миграция.
3. Создать свежий pre-change backup через ранее проверенный механизм и проверить его manifest. Если для изменяемого компонента нет успешного restore drill, deployment блокируется; новый непроверенный архив не считается защитой.
4. Развернуть сначала canary/один экземпляр, выполнить smoke tests.
5. Проверить health, error rate, latency, очередь, cost и внешние receipts.
6. Расширить rollout либо немедленно остановить его по порогам.
7. Зафиксировать deployment receipt и фактические версии.

## 3. Health, метрики и оповещения

Минимальные endpoints:

- `live` — процесс отвечает; не проверяет внешние зависимости;
- `ready` — Core, очередь и обязательные хранилища доступны;
- `version` — commit, artifact, schema и policy versions без секретов.

Минимальные метрики с tenant-safe labels:

- задачи по состояниям, возраст очереди, throughput;
- latency и error rate по boundary/adapter;
- повторные события, idempotency conflicts и rejected approvals;
- L1/L2/L3 failure rate и длительность;
- WAITING_HUMAN age и approval expiry;
- внешние действия и unknown outcome;
- CPU, RAM, disk, connection pool и storage growth;
- токены, model/tool calls и стоимость по задаче/tenant;
- возраст последнего успешного backup и restore drill.

Telegram не может быть единственным каналом оповещения, потому что сам является зависимостью системы. До production владелец должен утвердить независимый канал: например email, телефонный pager или внешний incident service. Critical alert требует повторной доставки и escalation, пока не подтверждён человеком.

## 4. Уровни инцидентов

| Уровень | Пример | Первое действие |
|---|---|---|
| SEV-1 | утечка данных, неверный платёж, cross-tenant, потеря контроля доступа | глобальный kill switch, изоляция, уведомление владельца |
| SEV-2 | внешние записи дают ошибки, недоступен Core, неизвестный outcome | остановить adapter/tenant, сохранить evidence |
| SEV-3 | деградация, растущая очередь, сбой отдельной функции | ограничить нагрузку, диагностировать |
| SEV-4 | локальный дефект без влияния на данные | записать и исправить обычным релизом |

Для SEV-1/2 нельзя «чинить наугад». Сначала ограничивается ущерб, фиксируются server timestamps, версии, request IDs и хэши артефактов. Секреты и сырые персональные данные в incident report не копируются.

До production владелец утверждает для каждого SEV target времени acknowledgement, назначения incident owner, escalation route и cadence обновлений. Пока значения TBD и независимый канал не проверен учением, production readiness считается проваленной.

### Базовый playbook

1. Подтвердить сигнал независимым наблюдением.
2. Включить scoped kill switch; при неизвестном масштабе — глобальный.
3. Сохранить неизменяемый audit snapshot и список затронутых tenant/task.
4. Подготовить отзыв/ротацию credentials при подозрении на компрометацию и выполнить её только после action-bound L4; до этого ограничить ущерб внутренним kill switch.
5. Назначить incident owner и вести timeline по серверному времени UTC.
6. Выбрать rollback, forward-fix или restore на основании проверяемых данных.
7. Перед возобновлением выполнить regression, security и reconciliation checks.
8. Оформить root cause, prevention и проверку восстановления.

## 5. Безопасная остановка и запуск

При штатной остановке:

- прекратить приём новых задач;
- дать ограниченное время текущим read-only операциям;
- не запускать новые внешние записи;
- сохранить checkpoints и leases;
- пометить незавершённые внешние вызовы как `UNKNOWN`, а не повторять автоматически.

При запуске:

- проверить конфигурацию, schema и secret references;
- восстановить очереди и истёкшие leases;
- reconcile `UNKNOWN` по idempotency/receipt;
- не считать просроченные approvals действующими;
- включать adapters только после health и policy checks.

### Локальный Telegram runner MVP-1 (CURRENT)

Запуск выполняется из корня канонического репозитория под owner Windows account:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe scripts\run_telegram_mvp1.py --serve --timeout 30 --announce
```

Preflight: чистые `main` и `agent/telegram-live`, exact owner binding, credential в Windows Credential Manager, Python 3.12 и точные четыре SQLite runtime-БД с ожидаемыми DDL fingerprints, application digests и `quick_check=ok`. Runner сверяет bot identity, выбирает CLI только после успешного `codex --version`, затем до объявления «готов к работе» выполняет через production `CodexCliAdapter` сетевой read-only sentinel: тот же Windows Job, auth, sandbox, environment и JSONL parser, но без durable Task. Probe использует tool-less `model.inference`: shell, shell snapshot, apps, MCP, web и local file tools выключены. Любой start/timeout/protocol/output failure останавливает запуск; ложный online-статус не публикуется.

До начала polling runner также прогревает `faster-whisper base/int8` из локального runtime cache с `local_files_only=True`. Порядок fail-closed: Codex startup probe → локальный warmup Whisper → создание control plane → polling и объявление готовности. Если локального snapshot нет или warmup завершается ошибкой, бот не публикует ложную готовность и не пытается разрешать или скачивать модель из сети при первом голосовом сообщении.

Точная голосовая команда подтверждённого владельца после локальной транскрипции сразу ставится в durable очередь и имеет ту же силу, что точная текстовая команда. Второй callback для обратимого действия не создаётся. Если распознано удаление или другое необратимое действие, бот подготавливает отдельное action-bound L4 с точной целью; без этой кнопки эффект не выполняется. Telegram worker использует exact профиль `gpt-5.6-sol`, `model_reasoning_effort=high`, `service_tier=fast`, `features.fast_mode=true`; answer-профиль остаётся tool-less, research получает только web search, а MCP выключен. Startup sentinel использует тот же профиль и fail-closed останавливает запуск, если модель, fast tier или auth недоступны. Fast mode уменьшает latency, но расходует кредиты быстрее; это эксплуатационный trade-off, а не ослабление reasoning.

Валидный L4/patch callback привязан также к source `message_id`. `answerCallbackQuery` и `deleteMessage` запускаются параллельно с независимыми двухсекундными deadline. После нажатия исходная карточка удаляется целиком; временная ошибка удаления не отменяет и не теряет уже принятое действие. Невалидная или повторная кнопка карточку не удаляет. Исходный voice envelope сохраняется для TaskContract/recovery; callback envelope создаётся только для отдельного L4 или применения patch.

После durable admission бот создаёт одну карточку прогресса и редактирует её на безопасных стадиях `контекст`, `Codex`, `L1`, `L2`, `L3`; каждые 30 секунд обновляется elapsed heartbeat. Это операционные статусы, а не скрытые рассуждения: prompt, raw payload, локальные пути, секреты и технические идентификаторы не публикуются. После доставки результата или безопасной ошибки промежуточная карточка удаляется либо превращается в единственную финальную ошибку, если recovery не может завершить outbox.

Owner-bound task contract может получить `owner.library.read` для точного server-owned корня `C:\Хранилище\АГЕНТ`. Adapter фиксирует resolved root и directory identity, а trusted server строит только bounded относительный path index. Обычный answer, owner index и startup probe выполняются tool-less: shell, shell snapshot, apps и MCP выключены; owner root не добавляется в argv и prompt, содержимое файлов не пересылается. Owner permission запрещено при `repo.write` и `web.search`; public research получает только model inference и строго валидированные `web_search` events, без shell, local-file, apps и MCP. Выдачу файла владельцу выполняет отдельный server-side file-transfer. `C:\Хранилище\WORK` находится вне owner root и не сканируется.

Server-side path index без symlink/junction по явному поисковому запросу просматривает не более 50 000 entries и передаёт до 8 относительных путей как подсказку. Сам Codex не может открыть эти файлы: owner root отсутствует в его argv и prompt. Отправку выбранного файла владельцу выполняет отдельный trusted file-transfer; анализ содержимого требует отдельного data-handling gate.

CURRENT caveat: Python runner работает под desktop account без отдельной Windows ACL, поэтому server-side scan остаётся доверенным компонентом. Реальный synthetic probe показал, что native-Windows shell read нельзя ограничить permission profile: соседний и deny-файл читались. Поэтому прямой owner filesystem scope для Codex запрещён; будущая замена требует доказанного negative-read теста.

Telegram document upload реализован для owner-bound `/file`: адаптер повторно проверяет разрешённый тип, размер, корень и стабильную identity открытого файла, после чего отправляет его через `sendDocument`. Подтверждённый эффект и его delivery receipt входят в durable Queue 2; остаётся явно документированное at-least-once окно между принятием файла Telegram и локальной записью receipt.

Telegram long poll до 30 секунд и request timeout до 60 секунд ограничены polling lease 240 секунд. Accepted text и локально распознанный owner voice после durable prepare ставятся во внутреннюю FIFO-очередь; handler не ждёт Codex. Два read-only workers выполняют независимые draft/answer параллельно. Admission допускает до 32 ожидающих drafts; общий maxsize 40 сохраняет резерв для L4. Overflow делает до трёх terminalization attempts и ACK-ается только после повторного чтения exact terminal Task из durable store. Owner-confirmed patch получает эксклюзивный доступ к обоим слотам на L2/L3/apply/commit. `/status` показывает `В работе`, `В очереди`, `Сбойных задач` и явно помечает очередь, требующую operator reconciliation.

`/limit` не ставится в task queue и не запускает model turn. На каждый запрос создаётся отдельный Codex app-server под тем же sanitized environment и Windows Job, отправляются только `initialize`, `initialized` и `account/rateLimits/read`, после ответа process tree завершается. Принимается exact bucket `codex` с окном 10 080 минут; результат показывает использованный/оставшийся процент и server reset time. Абсолютное число токенов OpenAI не раскрывает. Протокол ограничен 32 JSONL-сообщениями, 64 KiB stdout, 16 KiB stderr и 15 секундами; malformed/ambiguous response и provider failure возвращают безопасное «Лимит Codex сейчас недоступен» без Task и технических деталей.

Gate 5A.4 worker contract имеет deadline 10 800 секунд (3 часа, включая запас для двухчасовой работы); абсолютный schema/adapter ceiling равен 14 400 секундам. Один retry разрешён только для раннего `worker_start_failed`, `worker_failed` или `worker_protocol_error` и делит исходный execution deadline; timeout, policy error и внешний эффект не повторяются. Safe error code сохраняется в audit без stderr/prompt/path. Длительность worker больше не входит в polling lease.

### Историческая семантика до Queue 1/2

Удалена из активного runbook. Действуют правила раздела «Operational override 2026-07-24» и ADR 0011.

### Локальная проверка Windows Job guard

Runner разрешено запускать только после отдельного L4 на локальные child processes:

```powershell
.\.venv\Scripts\python.exe scripts\live_windows_job_probe.py --json
```

Приёмка требует `status=PASS` для normal exit, explicit tree kill и adapter cancellation, затем отдельную проверку: процессов `windows-job-probe.exe` и `windows_job_helper.py` нет, каталог `tmp` отсутствует. Runner не запускает сеть, credentials или Codex и не доказывает безопасность реального Codex sandbox.

## 6. Rollback

Rollback не обещает нулевой потери данных. Он возвращает код/конфигурацию к совместимой версии; уже выполненные внешние действия требуют отдельной компенсации и L4.

Порядок:

1. остановить rollout и новые внешние записи;
2. определить artifact/schema compatibility;
3. выполнить заранее проверенный rollback либо forward-fix;
4. проверить целостность, очереди, idempotency и tenant isolation;
5. сопоставить внешние receipts с audit log;
6. зафиксировать фактическую потерю/расхождение, не скрывая его;
7. возобновить работу только после L1–L3 и применимого L4.

## 7. Backup и восстановление

### Политика

- RPO и RTO для production сейчас **TBD**. До их утверждения владельцем и проверки нагрузочными/restore тестами production запуск блокируется.
- Backup шифруется отдельным ключом, хранится вне основного хоста и учётной записи, имеет контроль целостности и ограниченный доступ.
- Копируются состояние Core, audit/approval events, tenant artifacts, конфигурационные manifest и необходимые metadata. Секреты резервируются механизмом secret store, а не файлами `.env`.
- Retention backup согласуется с `10-Политика-памяти.md`; backup не даёт права хранить данные дольше установленного срока.
- Для критичных данных требуется защита от изменения/удаления на период retention.

Частота full/incremental backup, географическое размещение и число копий будут установлены после утверждения RPO/RTO и модели угроз. До этого нельзя заявлять гарантию «без потери данных».

### Restore drill

Restore считается проверенным только если в изолированной среде:

1. выбран backup, не известный заранее оператору проверки;
2. проверены manifest, подпись/хэш и возможность расшифровки;
3. восстановлены база, объекты и совместимые версии приложения;
4. выполнены schema, referential, tenant-isolation и sample business checks;
5. сопоставлены audit events и внешние receipts;
6. измерены фактические RPO/RTO;
7. сохранён отчёт без секретов с verifier identity и server timestamps.

Restore drill выполняется регулярно с частотой, которую задаст утверждённая recovery policy, и обязательно после изменения схемы backup/restore. Недоступный, неполный или непроверенный backup считается отсутствующим.

## 8. Отказы внешних зависимостей

### Telegram недоступен

- Core продолжает безопасные локальные задачи, если policy это допускает.
- Новые L4 не принимаются; pending approvals не продлеваются.
- Оповещение идёт через независимый канал.
- После восстановления updates обрабатываются по `update_id`; просроченные callbacks отклоняются.
- Для emergency L4 заранее настраивается независимый аутентифицированный канал либо локальная owner-console с теми же identity, action digest, TTL и audit rules. Он не обходит L4 и не разрешает автоматические действия; без проверенного канала credential rotation остаётся заблокированной, а ущерб ограничивается внутренним kill switch.

### LLM или tool provider недоступен

- startup sentinel не позволяет объявить Telegram-бота готовым, если CLI/auth/network/JSONL boundary не прошли;
- во время задачи различаются безопасные `worker_start_failed`, `worker_timeout`, `worker_protocol_error`, `worker_output_too_large`, policy/configuration и общий `worker_failed`;
- ограниченный retry применяется только к идемпотентному read-only запуску и только внутри исходного deadline;
- после лимита задача получает `FAILED` либо `ESCALATE`; пользователю отправляется одно короткое сообщение без технических ID и утверждений про L4;
- внешний вызов с неизвестным исходом не повторяется вслепую.

### Хранилище недоступно

- новые state transitions и внешние действия запрещены;
- нельзя принимать подтверждение, которое нельзя атомарно записать;
- после восстановления выполняется consistency check до снятия kill switch.

## 9. Логи и доступ

Логи структурированы и содержат `request_id`, `task_id`, `tenant_id`, event type, безопасный status, version и server time. Запрещены tokens, credentials, cookies, raw voice, полный prompt с клиентскими данными и payload внешнего действия. Чувствительные поля редактируются до передачи logger.

Доступ выдаётся по минимальным ролям, регулярно пересматривается и отзывается при offboarding. Администраторские операции фиксируются отдельно. Детальная классификация и retention определены в `10-Политика-памяти.md`.

## 10. Готовность к production

Production запрещён, пока отсутствует хотя бы один пункт:

- постоянное транзакционное хранилище и миграции;
- production-grade tenant isolation, Telegram credential rotation/supervision и полная replay protection;
- L1–L4 enforcement и immutable audit trail;
- secret store, network/tool/filesystem allowlists;
- мониторинг и независимый канал оповещений;
- kill switch и reconciliation unknown outcomes;
- утверждённые и воспроизведённые RPO/RTO;
- проверенный backup/restore и rollback;
- staging E2E и security review;
- L4 на конкретный deployment.

Правила внешних действий описаны в `07-Правила-внешней-записи.md`, evidence и релизные gates — в `06-Регламент-качества-L1-L4.md`, отчёты — в `09-Стандарты-отчётов.md`.

## Queue 1/2 activation runbook

### До L4

1. `DEBUG=false python -m pytest -q --disable-warnings`.
2. `python -m compileall -q src scripts tests`.
3. `git diff --check`, `pip check`, независимый L2/L3.
4. Убедиться, что live worktree и scheduled task не изменялись.

### Точный L4 activation

1. Остановить существующий `NobusSpaceBot`.
2. Создать owner workspace через `scripts/initialize_owner_workspace.py` с exact
   approval reference.
3. Fast-forward чистой live-ветки только до принятого commit.
4. Запустить `ops/windows/Install-NobusSpaceBot.ps1`; проверить один process tree.
5. Опубликовать команды через `scripts/configure_telegram_profile.py`.
6. Проверить startup Codex probe, offline Whisper warmup и свежий polling lease.
7. Выполнить owner smokes: text, direct reversible voice, voice-delete L4, queue ≥5, research with citations,
   document create/send, bounded download/send. Network command проверять отдельно.

### Health, backup and restore

- Read-only health: `scripts/check_telegram_health.py`.
- Backup только в новый каталог: `scripts/backup_telegram_runtime.py <new-dir>`.
- Restore требует остановленного runner, manifest verification и exact L4:
  `scripts/restore_telegram_runtime.py <manifest> --approval-ref <ref>`.
- После restore выполнить `quick_check`, startup и no-duplicate reconciliation.
- Реальный process-kill/reboot и restore drill нельзя считать пройденным по unit tests;
  он фиксируется только после owner L4.
## Final MVP-1 release checklist

1. Убедиться, что candidate worktree чист после локального commit и не имеет remote.
2. Выполнить полный pytest, compileall, `pip check`, `git diff --check`, secret scan
   и независимые L2/L3.
3. Остановить Task Scheduler job и создать проверенный backup всех четырёх
   runtime-БД до изменения live-ветки.
4. Fast-forward чистую `agent/telegram-live` только на принятый local commit.
5. Применить профиль/меню, переустановить Task Scheduler, выполнить startup
   Codex probe и локальный Whisper warmup до начала polling.
6. Проверить health, свежий lease, queue recovery, backup/restore dry drill и
   owner smokes: answer, voice, research, file send/analyze, document,
   Calendar/Tasks/Drive и Business Notes.
7. При P0/P1 остановить candidate, восстановить БД из backup и вернуть прежний
   live commit. Remote и push запрещены.
