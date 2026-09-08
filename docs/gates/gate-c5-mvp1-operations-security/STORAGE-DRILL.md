# C5: хранилища, резервирование и восстановление

Статус области: **PASS**; итоговый Gate определяется [ACCEPTANCE.md](ACCEPTANCE.md). Это стенд с настоящими SQLite, WAL, Windows DPAPI и Windows Job, синтетическими данными и отдельными каталогами. SDK, ASR и внешняя доставка не запускались. Полный продуктовый RTO не измерен.

Измерения `storage-tests-06` привязаны к фактическому application digest в [STORAGE-RECEIPTS.json](STORAGE-RECEIPTS.json). Последующие изменения runtime-agent изменили общий digest приложения; прежний hash не заменяется новым. Собственные production-файлы storage после run06 не менялись; их SHA-256 и время изменения записаны в receipt. Окончательные L1/L2 по замороженной source revision публикуются отдельно в Gate evidence. После run06 изменён только запас времени inherited тестовой фикстуры и документация.

## Фактический состав

Состав получен из `scripts/run_telegram_mvp1.py` и `runtime_database_paths`, а не из старого списка четырёх обязательных файлов.

| Файл | Роль и таблицы | Снимок |
| --- | --- | --- |
| `telegram-checkpoint.sqlite3` | `telegram_polling_checkpoints`: offset, lease, revision | Обязателен |
| `task-runtime.sqlite3` | `task_snapshots`, `ingress_claims`, `audit_events`: задачи, принятие и аудит; `sealed_answers`, `outbox_messages`, `outbox_receipts`, `outbox_delivery_parts`: ответ и доставка по частям; `miniapp_auth_replays`, `miniapp_session_recovery`, `miniapp_requests`: C4 replay, сессии и журнал запросов; `miniapp_restore_fence`: C5 cutoff и остановка приёма | Обязателен, 11 таблиц |
| `telegram-state.sqlite3` | `telegram_jobs`, `telegram_capabilities`, `semantic_clarifications`, `telegram_progress`: очередь, voice, подтверждения, состояния действий | Обязателен |
| `business-notes.sqlite3` | `business_notes`: неактивное legacy-расширение | Включается, если существует |
| WAL/SHM | Служебные файлы SQLite | WAL-коммиты входят в SQLite backup; SHM не является отдельной прикладной записью |
| Локальный TXT | Проекция результата из sealed/outbox | Восстанавливается из запечатанных байтов; не заменяет result/evidence |

Пустая четвёртая БД не создаётся. Пропуск присутствующей legacy-БД запрещён. Любой отсутствующий файл из аутентифицированного состава останавливает restore. Старые тестовые наборы с четырьмя файлами поддержаны тем же правилом.

## Версия, ключ и назначение

Backup удерживает singleton и writer reservations всех БД до чтения снимков. Проверяются точные DDL, SQLite integrity, прикладные digest и связи request → ingress. Logical state digest включает WAL-коммиты, replay и receipts; состояние источника после копирования обязано совпасть со снимком. При корректно остановленном runtime это предотвращает смешение разных моментов.

Manifest v3 аутентифицирован текущим пользователем Windows через DPAPI. Он содержит source binding, имена файлов, размеры, encrypted/plaintext SHA-256, logical state digest, digest схемы и digest `src/**/*.py`, `scripts/*.py`, `requirements.txt` с нормализованными переводами строк. Git HEAD сохраняется как происхождение; restore сравнивает реальные байты приложения и схему, поэтому документационный commit допустим. Неаутентифицированный journal v1 не принимается.

БД целиком зашифрованы существующим chunked DPAPI codec; открытый SQLite существует только в собственном staging во время операции. Manifest появляется после удаления staging. Лимит одной БД — 48 MiB под 80 MiB JSON codec; предупреждение health — 36 MiB для DB+WAL. Backup проверяет место `3 × сумма размеров снимков + 16 MiB`; ошибка записи не оставляет успешного manifest. Это ограниченный MVP, не обещание резервирования любого размера.

Restore требует точные manifest digest, target binding и owner approval ref. DPAPI, размер и хэш проверяются до открытия staged SQLite. Exact DDL проверяется до `quick_check`; SQLite DEFENSIVE включается, TRUSTED_SCHEMA выключается. Отсутствие этой возможности останавливает проверку. Установленная SQLite остаётся 3.53.1; бинарный риск описан в [DEPENDENCIES.md](DEPENDENCIES.md). Поддержки произвольных загруженных SQLite нет.

Новый target допускается после проверки назначения. Существующий target допускается только с полным составом и точным logical-state совпадением со снимком. Новая принятая запись, auth replay или offset после snapshot запрещают перезапись. Частичный набор, orphan sidecars, занятый writer и неподтверждённый journal останавливают операцию. Journal v2 связывает назначение, identity staging и хэши прежних/новых файлов; весь набор проверяется до rollback.

## Проверки и измерения

| Проверка | Результат |
| --- | --- |
| Шифрованный snapshot с настоящим WAL; sealed answer, tenant boundary, C4 cancelled/UNKNOWN request | PASS |
| Подтверждённая часть доставки 0 и неподтверждённые 1, 2 | Возобновлены только 1, 2; часть 0 не повторена |
| Pending действие и завершённое действие с receipt | Pending → UNKNOWN; завершённое доказательство сохранено |
| InitData, потреблённое после snapshot, и timestamp ровно на cutoff | Отказ после restore; старый recovery token отозван |
| Испорченный/пропущенный файл, неверная версия/цель, недостаток места, busy SQLite | Отказ до установки нового состояния |
| Новая принятая запись в существующем target | Старый snapshot не перезаписывает target |
| Исключение после первой замены файла | Rollback; исходные logical state digest совпали |
| Настоящий процесс завершён перед второй заменой, exit 71 | Следующая recovery восстановила исходное состояние; Job пуст |
| Подмена journal, traversal, чужая запись staging, настоящий hardlink | Отказ; внешний synthetic fixture сохранён |
| Ошибка очистки staging или temporary TXT | Видимая ошибка; sealed result не изменён |

Измерение run06, application digest `sha256:60212186c0449fb4032a1234bd1a51c2fd963f9c30d95e982ac8186d90cbc47b`:

| Операция | Секунды |
| --- | ---: |
| Backup | 0.497730 |
| Staged restore + validation | 0.643620 |
| Возраст snapshot при имитированном отказе | 0.309373 |
| Исключение при установке + rollback | 0.822953 |
| Запуск и аварийная остановка отдельного процесса | 1.652353 |
| Recovery journal после аварии | 0.065958 |

Размеры открытых БД стенда: task 131072 B, checkpoint 12288 B, state 53248 B. Потеряно 0 принятых задач и 0 подтверждённых частей; повторено 0 подтверждённых частей. Это не доказывает отсутствие неизвестных внешних действий после произвольного старого snapshot.

В агрегатном запуске — 212 PASS и один inherited timing fixture: срок 0.15 s истёк до входа в ожидаемую coroutine под нагрузкой. В тесте запас увеличен до 0.75 s; реальная отмена, отсутствие позднего результата и очистка сохранены. Две точные повторные проверки прошли. Полная итоговая L1 принадлежит Gate; WIP результаты и причины расхождений сохранены в JSON.

## Restore hold и сверка до C6

Любой успешный restore удаляет поколения сессий, ставит auth cutoff и durable `reconciliation_required=1`, удаляет временные callback/clarification capabilities. Runtime startup и новая Mini App авторизация останавливаются. Pending effect становится UNKNOWN; receipts, запечатанные результаты, replay и журнал запросов сохраняются. Автоматического сброса hold нет.

Перед отдельно разрешённым C6 владелец сверяет интервал от snapshot до отказа: принятые Telegram update/idempotency keys и C4 requests; UNKNOWN и выполнявшиеся действия; внешние подтверждения сообщений/документов; outbox по частям. Доказанную доставку отмечают без повторной отправки. Неизвестный исход не является разрешением на повтор. Необходимые записи восстанавливают из подтверждённых evidence, проверяют связи и делают новый backup. Только после отдельного точного решения владельца допустимы изменение hold и открытие приёма. Инструмента автоматической очистки hold в C5 нет.

## Retention и очистка

Владелец принял в этой задаче: RPO ≤ 24 h, целевой полный RTO ≤ 30 min, backup ежедневно и перед изменениями, 7 ежедневных и 4 еженедельных поколения. Расписание не включено, live-файлы не удалялись. Потеря диска того же ПК не покрыта; полный RTO с SDK/ASR остаётся измерением C6. Ранее принятое C2 voice TTL 1 h от immutable created_at и finished tombstone 24 h сохраняется.

Source-derived roots: `runtime/voice-temp` для файлового voice fallback, `runtime/codex-tmp` для isolated worker, canonical `.runtime/logs` для supervisor, явно заданный artifact root для TXT. В текущем isolated ASR audio передаётся в памяти; отдельного download spool нет. Модельный кеш не объявляется временным и не удаляется.

`check_telegram_health.py --runtime ROOT --details --retention-root label=ROOT` даёт ограниченный read-only inventory точных roots классов voice/temp/downloads/logs/staging. Он выводит hash назначения, числа и размеры, не следует symlink/reparse/hardlink; ownership — `unresolved_no_deletion`. Имя или расположение файла не даёт права на удаление. Dry-run стенда: четыре отсутствующих transient roots и 5 файлов backup (265087 B), удалено 0. Live roots storage drill не обследовал.

Положительная очистка относится только к новым staging и явно перечисленным файлам с проверенным dev/inode. Recursive delete не применяется. TXT temporary проверяет собственный inode и единственный допустимый hardlink на создаваемый target; ошибка удаления выводится безопасно, sealed result неизменен. Неустановленное владение и подмена пути останавливают очистку.

Operator health показывает application/schema binding, размеры DB/WAL, место, очередь и возраст, UNKNOWN, restore hold, возраст проверенного backup/drill либо unknown. Он не объявляет worker/ASR/ingress готовыми: это отдельная проверка runtime. Пороги и действия: [Runbook](../../08-Runbook-эксплуатации.md).
