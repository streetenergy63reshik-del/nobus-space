# M1-S1 — ремонт и сокращённая эксплуатационная приёмка

Статус: WIP, не принят. Решение владельца от 19.09.2026 в текущей задаче.

Историческое окно 16–19 сентября сохраняет NOT PASS. Новая приёмка относится
только к исправленной ревизии: независимые проверки единого кандидата, штатное
слияние и развёртывание, до 20 минут проверки после readiness, два успешных Health,
полный контролируемый backup и одна text/TXT квалификация (один вызов модели,
ASR 0), сохранность четырёх БД и отсутствие неизвестных эффектов.
Новое 72-часовое окно не требуется; heartbeat остаётся PAUSED; MVP2 не запускается.

Владелец разрешил относящиеся правки, изолированные проверки, commit/push/PR и
обычное слияние защищённой main, backup, контролируемое production-переключение
и stop/start трёх существующих заданий. Запрещены force push, обход защиты,
перемещение v1.0.2, откат БД, перезагрузка ПК ради теста и повтор неизвестных effects.

| Инцидент | Подтверждённый механизм / пробел | Исправление | Проверка | Результат |
|---|---|---|---|---|
| I01 | Public FAIL без исходной причины; падение не доказано | Типизированные bounded probes | HTTP/error/deadline/body | WIP |
| I02 | Public terminal, безопасный retry; внешний триггер UNKNOWN | Диагностика и сохранение порогов | Краткий и длительный отказ | WIP |
| I03 | Public terminal и незавершённая проверка старта | Стадия и отдельные результаты | Startup против steady | WIP |
| I04 | Startup relay STOP, backup restart78 и вторичный cleanup70 | Классификация relay, backup failure state | Copy→restart reject→cleanup→recovery | WIP |
| I05 | Scheduler сработал; starting без terminal блокирует reboot | Доказанное boot reconciliation | Безопасное продолжение и запреты | WIP |
| I06 | Health1 без причины при доступном runtime | Раздельные Health результаты | DB/route/probe failure | WIP |
| I07 | Relay_start255 STOP до бюджета; SSH причина UNKNOWN | Bounded transport retry | transient/permanent/UNKNOWN, budget | WIP |
| V01 | Неверный Host в диагностическом запросе | Единый local probe | Host/body/deadline | WIP |
| V02 | Console identity вместо production pythonw | Проверка эквивалентной identity | Несовпадение должно отклоняться | WIP |
| Наблюдение | Hold прерывал составную проверку; gaps не доказывают uptime | Независимые PASS/FAIL/NOT CHECKED | Hold и частичный отказ | WIP |

Исторические внешние первопричины могут остаться UNKNOWN. Ремонт должен доказать
устранение технических пробелов, а не задним числом объяснять потерянные данные.
Исходная ревизия 0bd63db, main 26860ad, PR32 уже слит и не повторяется.

## Контракт исправленного кандидата

Прерывание starting допускает автоматическое продолжение только при иной
Windows BootIdentifier (SystemBootEnvironmentInformation), корректной
аутентифицированной истории и binding. Supervisor владеет своим mutex, затем
захватывает Core и backup mutex, доказывает отсутствие старых детей/listener,
проверяет четыре БД, отсутствие действующей lease и неразрешённых задач/effects/
deliveries. Новый reboot_reconciled ссылается на прежний digest и BootIdentifier;
следующая попытка расходует прежний бюджет. Legacy starting без boot-доказательства,
неизвестность, повреждение или несовпадение остаются STOP. ПК ради проверки не
перезагружается. Получение boot GUID проверено реальным read-only Windows API.
Если прежняя lease ещё действует (production TTL240с), при доказанной смене boot
и отсутствии runtime допускается ограниченное ожидание до300с с неизменным
checkpoint digest под теми же mutex. Затем повторяются полная проверка и
отсутствие процессов. Изменение lease, превышение срока или unknown — STOP.
Защищённая capability в delivered с проверенным token/tenant/effect binding
считается завершённой; pending/executing/completed/unknown остаются STOP.
Завершённый effect job удаляется штатным ACK; произвольный finished для effect
не является допустимым состоянием существующего контракта.

Relay stderr читается только в ограниченную память (8192 байта) и не сохраняется.
Retry разрешают только завершённые однозначные OpenSSH transport diagnostics:
timeout/refused/reset/unreachable, после доказанного cleanup. Auth/key/host/config,
переполнение, неоднозначность и UNKNOWN — STOP. Новые authenticated terminal
сохраняют категорию и стадию; исторические schema3 не переписываются. Предел
остаётся initial+10 retries с паузой 60 секунд. Startup 360с, local/public
deadlines 2/5с, steady 3 неудачи с интервалом 10с не увеличены.

Readiness и Health используют один local probe с Host app.nobusspace.com и
точным телом {"status":"ready"}. Диагностический журнал сохраняет разрешённые
поля: boundary, PASS/FAIL, время, status/error class, elapsed/deadline, stage,
attempt. Health сохраняет allowlisted имя и результат каждой БД. Его объём
ограничен двумя сегментами по 1MiB. Health не перезапускает
Core; его FAIL и доступность маршрутов фиксируются отдельно. Наблюдатель
независимо читает DB, delivery, checkpoint, backup, hold и local/public; при
непроверенной task DB delivery — NOT CHECKED, а не нули. Read-only SQLite
соединения запрещают запись даже при ошибке вызывающего кода.

Backup отдельно сообщает VERIFIED generation и итог полного цикла.
failed_operator_required сохраняет generation, phase, причину, hold и cleanup;
отсутствие runtime проверяется до попытки повторного stop. Неизвестный процесс
или неизвестный результат не превращается в успешную остановку. Восстановление
после отказа использует прежний штатный exact-digest recover-failure; автоматическое
acknowledgement неизвестной аварийной серии не добавлено.
Начальное ожидание backup restart375с продлевается только по аутентифицированной
истории той же activation binding при переходе к следующей retry-попытке,
на startup360с + pause60с +15с запаса. Абсолютный предел цикла1140с оставляет
60с до существующего Scheduler limit20мин для cleanup. Permanent/UNKNOWN STOP
немедленно завершает ожидание. Readiness deadlines и retry-budget не изменены.
Новый restart journal допускает ровно дополнительное backup_status=VERIFIED;
его admission-разрешение ограничено19мин, legacy journal — прежними10мин.

## L1 и ограничения доказательств

- 280 PASS: operational repair, supervisor, L3/rework regressions, C5 runtime,
  C6 managed backup; локальная квитанция .runtime/m1-s1/repair-coherent-04.xml.
- 19 PASS зависимого C5 backup/recovery после изменения read-only SQLite:
  .runtime/m1-s1/repair-dependency-01.xml.
- 1 PASS отдельной проверки совместимого возврата кода: чтение смешанной истории,
  запрет rebind незавершённой серии, чистая остановка/rebind без потери истории.

Все отказы — отдельные state/порты/mutex или deterministic fixtures; production
не останавливался, provider/ASR не вызывались. Первые ошибки тестовой среды из-за
доступа sandbox к temp и старых fixture с production mutex классифицированы
как VERIFIER/ENVIRONMENT, исправлены отдельными namespaces. Исторические
успешные проверки неизменных областей не повторяются.

## Развёртывание и совместимый возврат

До переключения: сохранить точные Scheduler XML/launcher/config, свежую
проверенную generation и baseline четырёх БД; поставить hold, штатно остановить
единственную цепочку, доказать отсутствие процессов/lease и чистый history head.
Затем checkout точного проверенного source, StageDisabled существующих задач,
новый bound backup config, exact-head rebind под закреплённым pythonw и запуск.
Source, merge и deployed фиксируются раздельно. Новые действия используют новые
одноразовые квитанции; операторы PR32/18 сентября не повторяются.

Прямой возврат на 0bd63db несовместим с schema4. Для возврата подготовлен
[патч reader-совместимости](../../../../ops/windows/m1-s1-rollback-compat.patch):
он применяется только к 0bd63db, сохраняет прежний executable behavior и добавляет
чтение/валидацию новой истории и её recovery disposition. Автоматическое boot
reconciliation, новые probes и relay capture в rollback не включаются. Перед
deploy подготовить и зафиксировать точную rollback revision, проверить её состав.
Возврат допустим только после доказанной штатной остановки и exact-digest rebind
чистой истории, с пересчётом config/action bindings под rollback код и прежние
launcher/task definitions. Четыре production БД не заменять. При неизвестном
effect/cleanup или неразрешённой аварии — hold и операторский разбор, не reset.
Старую history не удалять, не восстанавливать из старой копии и не переписывать.

После readiness: ≤20 минут, два завершённых Health PASS, полный controlled backup
с возвратом ready и снятым hold; одна реальная owner text-задача с правильным
результатом/TXT, подтверждённой доставкой без дублей, один model call и ASR0;
четыре БД PASS, все прежние строки сохранены, offset не уменьшился, unknown/stuck
нет. Новые законные задачи учитываются, счётчики не обязаны остаться 87/85/16.
До выполнения этой части итоговая эксплуатационная приёмка не объявляется.

## Независимые замечания первого кандидата

Кандидат e128c39: L2 NOT PASS / L3 REWORK. До production выявлены и исправляются
одним пакетом: несовпадение backup_status с exact-key validator; STOP при ещё
действующей прежней lease после reboot; обрыв допустимого retry по375с backup
deadline; потеря отдельной DB-причины в Health; STOP для доказанно delivered
capability. Исходные отзывы и первый commit сохранены. Повторный разбор выполняют
те же L2/L3 по изменённым ветвям и зависимым контрактам; прежние успешные проверки
неизменных файлов не перезапускаются.
