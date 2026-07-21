# 08. Runbook эксплуатации

**Статус документа:** CANONICAL
**Состояние реализации:** TARGET; production-среда не создана
**Дата актуализации:** 21 июля 2026

Этот документ не подтверждает наличие описанных механизмов. До реализации, проверки и L4-разрешения платформа работает только локально с fake adapters и обезличенными данными.

## CURRENT и TARGET

**CURRENT:** существует локальный durable fake runtime с SQLite restart/recovery и injected delivery, но без deployment pipeline, production-хранилища, monitoring, secret store и recovery automation. Ни один раздел ниже нельзя трактовать как доказательство работающей эксплуатации.

**TARGET:** три изолированные среды, воспроизводимые релизы, наблюдаемость, независимые оповещения, проверяемые backup/restore, kill switch и процедурно подтверждённое восстановление.

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

### Локальная семантика Gate 4F

- завершённая durable задача после restart возвращается без повторного запуска worker;
- незавершённая задача возвращает `RECOVERY_REQUIRED` и требует явного reconciliation; автоматический resume запрещён;
- незавершённый voice challenge и pre-durable update/callback claims остаются process-memory: после transient failure нужен restart либо новый preview/confirm;
- injected status sender имеет at-least-once семантику; после успешной внешней отправки и crash до ACK возможен повтор, поэтому live adapter обязан иметь idempotency key;
- несовпадение сохранённого `destination_ref` с текущей tenant-конфигурацией не вызывает sender, фиксируется NACK и требует operator reconciliation;
- эти правила не являются production recovery automation и не разрешают сеть, credentials или live worker.

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

- не подменять модель без явно разрешённой policy/version;
- ограниченный retry с backoff применяется только к идемпотентным операциям;
- после лимита задача получает `FAILED` либо `ESCALATE`;
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
- tenant isolation, authenticated Telegram boundary и replay protection;
- L1–L4 enforcement и immutable audit trail;
- secret store, network/tool/filesystem allowlists;
- мониторинг и независимый канал оповещений;
- kill switch и reconciliation unknown outcomes;
- утверждённые и воспроизведённые RPO/RTO;
- проверенный backup/restore и rollback;
- staging E2E и security review;
- L4 на конкретный deployment.

Правила внешних действий описаны в `07-Правила-внешней-записи.md`, evidence и релизные gates — в `06-Регламент-качества-L1-L4.md`, отчёты — в `09-Стандарты-отчётов.md`.
