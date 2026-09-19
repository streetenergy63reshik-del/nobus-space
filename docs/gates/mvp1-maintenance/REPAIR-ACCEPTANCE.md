# M1-S1 — ремонт и сокращённая эксплуатационная приёмка

Статус: **M1-S1 CLOSED / ACCEPTED; MVP1 ACCEPTED — 19.09.2026, 17:50 МСК.**

Устойчивость принята по сокращённым критериям владельца от 19.09.2026 после исправлений и целевой проверки работающего бота. Повторное 72-часовое наблюдение не проводилось.

Итоговые доказательства — `EVIDENCE.current_acceptance_20260919`; историческое окно NOT PASS сохранено.

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
| I01 | Public FAIL без исходной причины; падение не доказано | [Типизированные bounded probes](../../../scripts/runtime_diagnostics.py) | [HTTP/error/deadline/body](../../../tests/test_m1_s1_operational_repair.py#L125) | Регрессии и live probes PASS; историческая причина UNKNOWN |
| I02 | Public terminal, безопасный retry; внешний триггер UNKNOWN | [Диагностика и сохранение порогов](../../../scripts/run_nobus_space_live.py) | [Порог длительного отказа](../../../tests/test_m1_s1_runtime_supervisor.py#L138) | Принятые supervisor-регрессии PASS; прежние пороги сохранены; внешняя причина UNKNOWN |
| I03 | Public terminal и незавершённая проверка старта | [Стадия и отдельные результаты](../../../scripts/run_nobus_space_live.py) | [Startup против steady](../../../tests/test_m1_s1_runtime_supervisor.py#L167) | PASS; live startup FAIL11:40:59 сохранён отдельно от ready11:41:51 |
| I04 | Startup relay STOP, backup restart78 и вторичный cleanup70 | [Классификация relay, backup failure state](../../../scripts/run_telegram_backup_cycle.py) | [Copy→restart reject→cleanup→recovery](../../../tests/test_m1_s1_operational_repair.py#L169) | Негативная регрессия PASS; полный live cycle complete/VERIFIED/ready PASS |
| I05 | Scheduler сработал; starting без terminal блокирует reboot | [Доказанное boot reconciliation](../../../scripts/reboot_recovery.py) | [Безопасное продолжение и запреты](../../../tests/test_m1_s1_operational_repair.py#L71) | Положительные и STOP-сценарии PASS; ПК не перезагружался |
| I06 | Health1 без причины при доступном runtime | [Раздельные Health результаты](../../../scripts/check_nobus_space_health.py) | [DB/route/probe failure](../../../tests/test_m1_s1_operational_repair.py#L253) | Регрессии и два live Health PASS; старый FAIL не отменён |
| I07 | Relay_start255 STOP до бюджета; SSH причина UNKNOWN | [Bounded transport retry](../../../scripts/runtime_diagnostics.py) | [transient/permanent/UNKNOWN, budget](../../../tests/test_m1_s1_operational_repair.py#L38) | Transient/permanent/UNKNOWN и budget PASS; внешняя причина UNKNOWN |
| V01 | Неверный Host в диагностическом запросе | [Единый local probe](../../../scripts/run_nobus_space_live.py) | [Host/body/deadline](../../../tests/test_m1_s1_operational_repair.py#L125) | PASS; live HTTP200 с точным телом; старый verifier FAIL сохранён |
| V02 | Console identity вместо production pythonw | [Проверка эквивалентной identity](../../../scripts/run_nobus_space_live.py) | [Несовпадение должно отклоняться](../../../tests/test_m1_s1_operational_repair.py#L116) | PASS; live pythonw binding098ef3f2; identity не ослаблялась |
| Наблюдение | Hold прерывал составную проверку; gaps не доказывают uptime | [Независимые PASS/FAIL/NOT CHECKED](../../../scripts/observe_nobus_runtime.py) | [Hold и частичный отказ](../../../tests/test_m1_s1_operational_repair.py#L194) | Hold/partial failure PASS; NOT CHECKED не подменяется нулём; gaps сохранены |

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
[патч reader-совместимости](../../../ops/windows/m1-s1-rollback-compat.patch):
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

5425db8 получил L2/L3 PASS и опубликован PR33 / merge335a157. При подготовке
переключения19.09 в11:18МСК найден новый platform-dependent пробел: после
доказанной штатной остановки socket connect_ex с1с возвращает10035, с3с —10061.
Прежний код безопасно сохранил STOP, но не мог подтвердить отсутствие listener.
До checkout и создания backup операция остановлена; БД и code/config не менялись.
Прежний source0bd63db запущен штатно один раз в11:23:27 после exact-head проверки
clean planned_stop, снятой lease и сохранности БД/backup. Это плановая пауза
развёртывания, не новый исторический инцидент и не успешная приёмка кандидата.

Новый delta заменяет socket-based absence проверкой Windows Get-NetTCPConnection
с выводом только числа listener. Ошибка команды, неизвестный результат или любой
listener на порту остаются STOP. Core/process/mutex проверки сохранены; readiness
deadlines2/5с не изменены. Изолированная регрессия использует выделенный ephemeral
порт и проверяет оба состояния: listener есть/закрыт. Требуется адресное closure
тем же L2/L3 и отдельная штатная публикация delta перед следующим переключением.

## Фактическое развёртывание 19.09.2026

Ремонт принят теми же независимыми L2/L3: пакет5425db8, затем точечный
Windows delta0c9b778. [PR33](https://github.com/streetenergy63reshik-del/nobus-space/pull/33)
и [PR34](https://github.com/streetenergy63reshik-del/nobus-space/pull/34) штатно слиты.
Source и deployed: `0c9b778ef59eb4cc01d3ab0c2ef9a14969801d83`;
merge: `8af1309af36eb3ab591186906975dd8cd3ac9880`. Их деревья одинаковы.
Совместимый код возврата: `220b396ba992a8b2668b5ea3fa632da6f10b7853`;
возврат БД не выполнялся и не разрешён. v1.0.2 не перемещался.

Дополнительно после пакетных замечаний:98 PASS и4 PASS затронутых ветвей;
Windows listener delta:8 PASS, включая реальный выделенный ephemeral port.
Хэши точных квитанций и полный deployment readback находятся в
`EVIDENCE.post_window_repair_20260919`; старые разделы evidence не изменены.

Перед переключением сохранены Scheduler XML, launcher/config и baseline.
Проверенная prechange-копия старого source создана11:33, копия с binding нового
кода —11:39. В разовом операторе обнаружены два невыполненных предусловия:
папка rollback до installer и новая code-bound копия до снятия hold.
Оба STOP сохранены; после readback продолжены только незавершённые шаги.
История, данные и старые копии сохранены; неизвестные внешние эффекты не повторены.

Запуск выдан11:40:14. Health11:40:59 сохранил FAIL: local deadline/public503
во время startup до readiness. Это не steady outage; последующий PASS не стирает
первоначальный результат. Health11:41:51 и11:42:52: все6 проверок PASS.
Отдельный probe11:42:07: local/public200, точное тело,265/688мс при2000/5000мс.

Единственный controlled backup запущен11:42:35; complete11:46:03,
Scheduler0, copy VERIFIED, hold снят, runtime ready. Generation:
`daily-20260919T114339-d3bc57fd7b6046b388022492ac5b40f1`.
Это полный успешный цикл, отдельно от двух prechange-копий.
Windowed verifier11:46:54 подтвердил production binding
`sha256:098ef3f231d54244f2d8fe35cfb6f2fb1de87a5d6fbbc367dea11abe1c044f25`.

Срез11:48:40: local/public PASS; одна цепочка supervisor/Core/relay, один
loopback listener8765 и active lease. Четыре БД PASS, все прежние строки
сохранены по хэшам, offset375633520 не уменьшился, revision65740.
Pending/leased/unknown/failed deliveries0, reconciliation=false.
Сохранённый `starting` относится к действующему здоровому runtime;
он не интерпретируется как брошенная попытка.

## Историческая пауза перед квалификацией — снята разрешением владельца

Text/TXT квалификация — NOT CHECKED. Задача не отправлена; вызовы исполнителя0,
semantic provider0, ASR0. Обычный включённый маршрут сначала вызывает semantic
compiler, затем исполнитель задачи. Буквальный лимит «один вызов модели суммарно»
не позволяет выполнить обе стадии. См.
[вход text-задачи](../../../src/application/telegram_product.py#L1311) и
[вызов compiler](../../../src/application/semantic_admission.py#L1872).
Владельцу задан вопрос: разрешён ли один вызов исполнителя со штатным отдельным
разбором запроса. До ответа реальные вызовы и изменение admission не выполняются.

Подготовлен один простой запрос: «Вычисли17+25 и верни только число42».
После уточнения требуется одна реальная owner-задача, правильный результат,
доступный TXT, подтверждённая доставка без дублей и целевой readback её effects.
Успешные неизменные L1–L3 и полный backup-цикл повторять не нужно.

Итоговую эксплуатационную приёмку и MVP1 ACCEPTED пока не объявлять.
Исторический JOURNAL-72H.md остаётся NOT PASS; heartbeat PAUSED; MVP2 не запущен.

## Окончательная эксплуатационная приёмка — 19.09.2026, 17:50 МСК

Владелец ответил «Разрешаю все необходимые действия» на точный вопрос о
штатном semantic-разборе и одном вызове исполнителя. Единственная text-задача
отправлена из личного Telegram владельца: «Вычисли17+25. Верни только итоговое
число без пояснений». Задача `269f3aa7-942d-4195-b073-b300453d7a28` завершена
`answered`, revision6; audit содержит один attempt: started→result_ready.
Штатный semantic-разбор выполнен отдельно; ASR0. Число внутренних сетевых
повторов провайдера из worker audit не выводится.

Правильный ответ42 и `nobus-result.txt`2байта видны в чате; файл доступен и
загружен. Обе delivery parts имеют ACK первой попытки в17:46:45 и один digest
`sha256:73475cb40a568e8da8a045ced110137e159f890ac4da883b6b17dc651b3a8049`.
Outbox acked, attempt_count1; дублей нет. Защищённая структурированная запись
ответа корректно разворачивается в текст42 и тот же TXT.

Readback17:50:10: четыре БД PASS; прежние строки сохранены и относительно
prechange, и относительно свежего qualification baseline. Теперь88tasks,
86receipts,18confirmed parts — прирост соответствует одной новой задаче.
Offset375633521 вырос на1; active lease, unknown/pending/leased/failed0,
reconciliation=false, hold отсутствует. Local/public200, точное тело,
313/609мс при прежних2000/5000мс. Binding и authenticated history head
не изменились со среза после backup: новых runtime exits в этой истории нет.

Принятые L1–L3, два Health, полный controlled backup и процессная цепочка
повторно не запускались. Короткая проверка состояла из двух частей:
11:41:51–11:48:40 и17:44:26–17:50:10МСК; между ними ожидалось разрешение
владельца на вызовы модели. Это не новое окно наблюдения; непрерывные20мин
наблюдения не заявляются. Собственно проверки обеих частей заняли менее20мин.

**M1-S1 CLOSED / ACCEPTED. MVP1 ACCEPTED.**
Устойчивость принята по сокращённым критериям владельца от 19.09.2026 после исправлений и целевой проверки работающего бота. Повторное 72-часовое наблюдение не проводилось.

Исторические I01–I07, V01/V02, NOT PASS и ограничения наблюдения сохранены.
Внешние исторические причины, оставшиеся UNKNOWN, не объявлены устранёнными.
Heartbeat PAUSED; три штатных задания production продолжают работать;
C6 не переоткрывался, MVP2 не запущен, v1.0.2 не перемещался.
