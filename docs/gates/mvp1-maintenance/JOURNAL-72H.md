# M1-S1 — полный журнал инцидентов 72-часовой проверки

## Итог и границы

Окно: **16 сентября 2026, 08:00 → 19 сентября 2026, 08:00 МСК** (UTC: 16.09 05:00 → 19.09 05:00). Срок не продлевался. Итог устойчивости — **NOT PASS**, M1-S1 остаётся OPEN, M2-G0 — BLOCKED.

Это сводный журнал всех выявленных и сохранённых событий в данном окне, а не утверждение, что в промежутках без наблюдений не было иных сбоев. Источники: [EVIDENCE.json](EVIDENCE.json), [подробный журнал 18 сентября](INCIDENT-20260918.md), сохранённые квитанции наблюдателя и восстановления. Данные задач, содержимое сообщений, credentials и сырые журналы в документ не включены.

Снимок источника EVIDENCE: updated_at = 2026-09-19T05:01:04.559878+00:00, SHA256 **9c2f18c891577e7dc3e3e4cf3aad04cd45f8b753bc719342dbe237ce139e78a4**. SHA256 INCIDENT-20260918.md: **368ddd27c57f9b195db3600b7627bc4839a3feb8f07ceb63bcd29b24da8ad20f**.

Проверявшийся source/deployed: **0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c**, merge/main: **26860adfeae84fa075a8f3cb3260e9d4c6dd9257**, release **v1.0.2** не изменён. Python закреплён до начала окна; новые неизвестные причины ниже нельзя объяснять старым Python drift без доказательств.

### Как считать события

- **7 зарегистрированных инцидентов** в EVIDENCE.observation.incidents относятся к этому окну; они разобраны в карточках I01–I07.
- **6 уникальных аварийных terminal-событий supervisor**: четыре public_readiness_failed и два relay_exit255. Повторная попытка может завершиться отдельно в рамках одного эпизода; это не шесть независимых длительных простоев.
- Отдельно подтверждена **серия перезапусков Windows**, после которой автоматический запуск бота был заблокирован.
- **3 операторских восстановления 18.09**: 07:40, 12:08, 20:04. Восстановленная доступность не равна исправленной первопричине.
- **1 проваленный плановый полный backup-цикл** 18.09; копия создана и цела, но автоматический запуск runtime не завершился. Плановые циклы 17.09 и 19.09 успешны — **2/2**.
- **2 доказанные ошибки диагностических средств** — V01 и V02. Они не считаются багами production.
- **6 зарегистрированных интервалов без наблюдений более 60 минут**. Их нельзя считать ни успешными проверками, ни шестью падениями бота.
- В observation сохранено **121 срез: 120 внутри окна и 1 заключительный после его границы**. Для 16 срезов внутри окна есть хотя бы один отрицательный признак по readiness/Health/новому аварийному завершению; среди них повторные проверки одного простоя и два незавершённых старта. Количество таких срезов не равно количеству инцидентов.

Все времена далее — МСК. UNKNOWN означает отсутствие достаточных доказательств причины. Приоритеты в разделе исправлений — предложение для разбора, а не уже согласованное изменение контракта.

## Хронология ключевых событий

| Время | Событие | Что произошло дальше |
|---|---|---|
| 17.09 09:59:39 | I01: внешний probe FAIL, local PASS, цепочка процессов прежняя | 10:01:11 внешний HTTP200; остановка runtime не подтверждена |
| 17.09 22:31:50 | I02: public_readiness_failed, попытка 1/10, cleanup proven | Автоповтор 22:32:50; обе проверки PASS в 22:37:04 |
| 18.09 03:04:31 | I03: public_readiness_failed, попытка 2/10 | Автоповтор 03:05:31; в 03:06 обе readiness FAIL, listener отсутствует |
| 18.09 03:19:03 | V01: scoped local HTTP400 из-за неверного диагностического запроса | Public HTTP200; корректное local readiness этим запросом не проверено |
| 18.09 03:25:13 | I04: повторный public_readiness_failed, попытка 3/10 | Cleanup proven, попытка 4 начата в 03:26:13 |
| 18.09 03:27:56 | I04: relay_exit255 на startup, попытка 4/10 | stop_non_retryable, cleanup proven; бюджет не исчерпан |
| 18.09 03:30:01–03:37:45 | I04: плановая копия создана, но restart получил 78; cleanup — 70 | failed_operator_required, admission hold, Main/Health отключены |
| 18.09 07:37–07:41 | Восстановление I04 по разрешению владельца | Exact acknowledgement и ручной recovery-цикл; PASS в 07:40:38 и независимый срез 07:41:56 |
| 18.09 11:11–11:14 | I05: перезапуски Windows | Последняя загрузка 11:14:28; инициатор и причина не установлены |
| 18.09 11:16:14–11:16:56 | I05: Scheduler вызвал Main, recovery_history_blocked/78 | previous_attempt_unknown; бот сам не восстановился |
| 18.09 12:05–12:08 | Восстановление I05 по разрешению владельца | Один Start; исходный FAIL в 12:07:38, HTTP200 в 12:08:03, подтверждение в 12:08:48 |
| 18.09 17:35:43 | I06: плановое задание Health завершилось с 1 | Бот доступен; следующий Health завершился с 0, подтверждено 17:37 |
| 18.09 18:50:44 | I07: public_readiness_failed, попытка 1/10 | Cleanup proven, автоповтор через 60 секунд |
| 18.09 18:51:46 | I07: relay_exit255 на relay_start, попытка 2/10 | stop_non_retryable, control_closed; бюджет не исчерпан |
| 18.09 20:00–20:04 | Восстановление I07 по разрешению владельца | Один Start; исходный FAIL 20:02:26, HTTP200 20:02:53, независимый PASS 20:04:35; V02 диагностирован отдельно |
| 19.09 03:30–03:32 | Второй успешный плановый backup-цикл | Полный цикл complete; не падение |
| 19.09 08:01:04 | Заключительный read-only срез | Бот доступен, данные целы; этот срез после срока не продлевает окно и не отменяет прежние отказы |

## Карточки инцидентов

### I01. Внешняя проверка не прошла, остановка бота не подтверждена

**ID:** PUBLIC_READINESS_20260917T065939. **Время:** 17.09 09:59:39.

Факт: local=true, public=false. Один runtime и активная lease сохранились; процессы не изменились, новых authenticated terminal events нет. Это отрицательная внешняя проверка, но не доказанное завершение процесса.

Один read-only повтор в 10:01:11 дал HTTP200, точное совпадение тела и 797 мс при бюджете 5000 мс. Исходный FAIL сохранён. Первопричина **UNKNOWN**: исходный boolean probe не сохранил HTTP-код/класс ошибки. Успешный повтор не восстанавливает причину задним числом.

Данные: четыре БД PASS, 87 задач / 85 receipts / 16 подтверждённых частей; unknown delivery=0, очередь пуста, reconciliation=false, offset не уменьшился. Состояние: доступность восстановлена к повторной проверке, причина не закрыта.

Доказательства: EVIDENCE.observation.incidents[id=PUBLIC_READINESS_20260917T065939]; [m1-s1-observation-20260917-0959.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260917-0959.json>); [m1-s1-observation-20260917-1001-public.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260917-1001-public.json>).

### I02. Аварийное завершение из-за public readiness с успешным автоповтором

**ID:** PUBLIC_READINESS_20260917T193150. **Время:** 17.09 22:31:50.

Authenticated terminal: stage=steady, public_readiness_failed, supervisor exit1, local=true/public=false, attempt1, retry_budget10, cleanup=proven. Отдельного причинного exit дочернего Core/relay не зафиксировано.

Автоповтор начат в 22:32:50 после 60 секунд; к 22:37:04 local/public PASS и новая единичная цепочка процессов. Ручного restart в этом эпизоде не было. Между terminal и подтверждающим срезом прошло 5 мин 14 с; это интервал до подтверждения, **не измеренная длительность недоступности**.

Первопричина **UNKNOWN**: событие указывает границу отказа public readiness, но не сетевое исключение/HTTP-код. Общая причина с I01 не доказана. Целостность данных и монотонность offset подтверждены. Состояние: автоповтор сработал; первопричина не устранена доказанным исправлением.

Доказательства: одноимённый incident в EVIDENCE; [m1-s1-observation-20260917-2237.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260917-2237.json>).

### I03. Ночной public-readiness отказ; восстановление полностью не доказано

**ID:** PUBLIC_READINESS_20260918T000431. **Время:** 18.09 03:04:31.

Authenticated terminal на steady: public_readiness_failed, supervisor exit1, local=true/public=false, attempt2/10, retry, cleanup proven. Попытка3 начата в 03:05:31.

В срезе 03:06:08 local/public=false, listener отсутствует, lease неактивна, хотя цепочка запускаемых процессов присутствует. Health после запуска 03:05:43 имеет LastTaskResult1. Это состояние запуска после реального terminal; нельзя объявлять runtime восстановленным только по наличию процессов.

В 03:19:03 public HTTP200 за906мс. Local HTTP400 получен ошибочным диагностическим запросом без обязательного Host — см. V01. Поэтому полное восстановление local/public в этом промежутке **не подтверждено**. В 03:25:13 последовало новое terminal-событие I04.

Четыре БД и сохранность агрегатов PASS; offset375633502. Первопричина public отказа **UNKNOWN**, связи с Python drift не установлено. Карточки I03 и I04 — соседние части одной ночной серии; их нельзя складывать как два независимых длительных простоя.

Доказательства: одноимённый incident в EVIDENCE; [m1-s1-observation-20260918-0306.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-0306.json>); [m1-s1-readiness-followup-20260918-0319.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-readiness-followup-20260918-0319.json>).

### I04. Relay завершился на startup; плановый backup не смог вернуть бота в работу

**ID:** BACKUP_RESTART_BLOCKED_20260918T003111. **Серия:** 18.09 03:25–07:41.

Подтверждённая цепочка:

1. 03:25:13: attempt3 — public_readiness_failed на steady, exit1, cleanup proven.
2. 03:26:13: начало attempt4.
3. 03:27:56: relay_exit255 на startup; stop_non_retryable, cleanup proven и закрытие recovery control. Это **4-я попытка из бюджета10**, не exhaustion.
4. 03:30:01: Scheduler начал плановый backup. Generation daily-20260918T033035-005adf9dd1ba492f83987e7cf36e2bee создана в03:30:36 и проверена.
5. 03:31:11: запуск runtime отклонён с recovery_history_blocked/78, поскольку завершённая аварийная серия ещё не подтверждена оператором.
6. 03:37:30: дополнительный stop_control_create_failed/70 при cleanup уже остановленного supervisor.
7. 03:37:45: cycle phase=failed_operator_required, admission_hold=true; Main и Health отключены, Backup LastTaskResult1. Полный плановый цикл **FAIL**, несмотря на целую копию.

Причина прекращения автоповторов доказана: действующий контракт допускает retry relay_exit только для подходящего steady-исхода; startup не подходит. Это подтверждённое поведение fail-closed, а **не доказательство ошибки реализации retry**. Его эксплуатационная пригодность требует отдельного решения, без ослабления правил вслепую.

Первопричина SSH/relay exit255 **UNKNOWN**: stderr направлен в DEVNULL, сохранённый код не различает транспортную, серверную и другую SSH-причину. Проверка SSH в07:33 показала текущую доступность, но не объяснила ночной отказ. Python drift не установлен.

Повторные срезы04:05,04:40,05:13,05:46,06:19,06:58 подтверждали тот же hold/простой, а не новые падения. Observer останавливался с RuntimeAdmissionPaused. Четыре БД отдельно проходили проверку; для этих scoped срезов delivery/reconciliation оставались **не проверены**, а не нулевыми по умолчанию. Полная отдельная runtime-проверка перед восстановлением прошла PASS. Поэтому широкая прежняя формулировка «full runtime validation blocked» не доказывает повреждение БД.

Восстановление по прямому разрешению: 07:37:18 exact acknowledgement; 07:40:38 штатный recover-failure завершился PASS. Ручная generation daily-20260918T073905-7f7fc943c2414c6b8bb211b33c3a7e1c и complete cycle **не считаются плановым успехом**. Независимый срез07:41:56 подтвердил доступность, единичный runtime/lease, целостность и сохранность строк.

От terminal03:27:56 до успешного recovery07:40:38 прошло4ч12мин42с. Это интервал между зафиксированными событиями, не поминутный журнал доступности. Причина внешнего сбоя осталась открытой.

Доказательства: EVIDENCE.observation.incidents[id=BACKUP_RESTART_BLOCKED_20260918T003111], operator_recovery_20260918; [INCIDENT-20260918.md](INCIDENT-20260918.md); [m1-s1-observation-20260918-0403-failed.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-0403-failed.json>); [m1-s1-paused-backup-diagnostic-20260918-0405.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-paused-backup-diagnostic-20260918-0405.json>); [m1-s1-recovery-readback-20260918-0741.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-recovery-readback-20260918-0741.json>).

### I05. После перезапусков Windows бот автоматически не запустился

**ID:** HOST_REBOOT_RECOVERY_BLOCKED_20260918T081656. **Время:** 18.09 11:11–12:08.

В Windows System сохранены три группы событий: 1074/6006/6005 в11:11:40–11:12:54,11:13:20–11:13:57 и11:14:04–11:14:52. LastBootUpTime — 11:14:28.500. Подтверждена серия перезапусков; инициатор в scoped диагностике **не исследован**, первопричина UNKNOWN. Это не доказанный SSH-сбой или Python drift.

Scheduler **сработал**: Main LastRunTime11:16:14, затем authenticated fallback11:16:56 с recovery_history_blocked/78. Прежняя попытка осталась на starting без terminal; recovery-state=blocked/previous_attempt_unknown. Следовательно, проблема не в отсутствии триггера Scheduler, а в блокировке запуска по незавершённой recovery history.

Срез11:54:38: оба readiness FAIL; процессов, listener8765 и активной lease нет. Все3 задания включены, Main78/Health1. Scoped повтор: local deadline2000мс; public HTTP502 за515мс. Четыре БД и данные целы. Backup1 — прежний ночной провал I04, не новый backup-инцидент.

По новому разрешению владельца: acknowledgement12:05, один Start Main12:06:35. Исходный post-start срез12:07:38 local/public FAIL сохранён. В12:08:03 обе проверки HTTP200 (359/828мс), в12:08:48 подтверждены Health0, один runtime и lease, сохранность строк. БД не откатывались, код/config/Actions/binding не менялись.

Автоматическое восстановление после перезагрузки фактически не состоялось; fail-closed причина известна, но данный эпизод не доказывает наличие безопасного автоматического продолжения незавершённой попытки. Требуется отдельный разбор контракта. Наличие перезагрузок не позволяет подтвердить 72 часа непрерывно включённого ПК.

Доказательства: одноимённый incident и operator_restart_after_reboot_20260918 в EVIDENCE; [m1-s1-observation-20260918-1154.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-1154.json>); [m1-s1-stop-diagnostic-20260918-1156.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-stop-diagnostic-20260918-1156.json>); [m1-s1-poststart-20260918-1207.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-poststart-20260918-1207.json>); [m1-s1-poststart-readback-20260918-1208.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-poststart-readback-20260918-1208.json>).

### I06. Задание Health завершилось с ошибкой при доступном боте

**ID:** HEALTH_TASK_FAILURE_20260918T143543. **Время запуска:** 18.09 17:35:43.

В срезе17:36:13 Health Ready/LastTaskResult1. При этом local/public=true, один runtime и active lease, процессы неизменны, новых terminal/fallback events нет, четыре БД PASS. Остановка бота **не подтверждена**.

Следующий плановый Health17:36:43 завершился0, readback17:37:00. Один диагностический срез17:36:58 дал local/public HTTP200 за219/844мс при бюджетах2000/5000мс.

Первопричина **UNKNOWN**: числовой LastTaskResult1 не показывает, какая именно проверка отказала. Следующий0 не отменяет первый1. Нельзя без доказательств называть это ни ложным срабатыванием, ни падением Core.

Доказательства: одноимённый incident в EVIDENCE; [m1-s1-observation-20260918-1736.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-1736.json>); [m1-s1-health-diagnostic-20260918-1737.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-health-diagnostic-20260918-1737.json>).

### I07. Вечерний public отказ, relay_exit255 и остановка до вмешательства владельца

**ID:** RELAY_NON_RETRYABLE_STOP_20260918T155146. **Серия:** 18.09 18:50–20:04.

После успешного среза18:44:29:

- 18:50:44: attempt1/10, public_readiness_failed на steady, cleanup proven, ожидание60с.
- 18:51:46: attempt2/10, relay_exit255 на relay_start, stop_non_retryable, cleanup proven, control_closed.
- 19:16:36: local/public FAIL, процессы/порт/active lease отсутствуют; MainReady1/HealthReady1, все задания включены.
- 19:17:05: local DEADLINE_EXCEEDED2016мс при бюджете2000; public HTTP502 за1125мс при бюджете5000.
- 19:50 и19:57: тот же простой, новых terminal events нет.

Бюджет10 не исчерпан. Механизм STOP совпадает по классу с ограничением startup/relay_start, но **общая внешняя первопричина с ночным событием не доказана**. SSH/public причина UNKNOWN; stderr не сохранён. Четыре БД,87/85/16,unknown0,пустая очередь и reconciliation=false сохранены. Backup1 всё ещё относится к I04.

Новое операторское разрешение использовано один раз: acknowledgement20:00, Main Start20:01:35. Исходный срез20:02:26 local/public FAIL сохранён. Один scoped повтор20:02:53 — HTTP200,281/1109мс; независимый срез20:04:35 — PASS и Health0. Данные сохранены; source/config/Scheduler Actions/binding неизменны. Нового backup не создавали.

От terminal18:51:46 до независимого подтверждения20:04:35 —1ч12мин49с. Это не измеренный до секунды непрерывный downtime. Доступность восстановлена, первопричина не закрыта.

Доказательства: одноимённый incident и operator_recovery_relay_evening_20260918 в EVIDENCE; [m1-s1-observation-20260918-1916.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-1916.json>); [m1-s1-stop-diagnostic-20260918-1917.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-stop-diagnostic-20260918-1917.json>); [m1-s1-observation-20260918-2002-startup.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-2002-startup.json>); [m1-s1-observation-20260918-2004-recovered.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-2004-recovered.json>).

## Ошибки диагностики и ограничения доказательств

### V01. Scoped local probe без обязательного Host

18.09 03:19 локальный запрос получил HTTP400 за156мс, поскольку диагностический helper не передал обязательный Host app.nobusspace.com. Это **VERIFIER_DEFECT**, а не контрактно эквивалентная проверка readiness и не доказанное новое падение бота. Public HTTP200/906мс остаётся валидным отдельным результатом; local остаётся непроверенным этим повтором.

Ошибочный результат сохранён. Для дальнейших scoped проверок использовался корректный helper с Host, прежними deadline и точным ожидаемым телом; критерий readiness не ослаблялся. Исходный FAIL штатного observer03:06 этим дефектом не отменяется.

Источник: EVIDENCE incident PUBLIC_READINESS_20260918T000431, followup_local_diagnostic_status; [m1-s1-readiness-followup-20260918-0319.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-readiness-followup-20260918-0319.json>).

### V02. Проверка activation binding под неверным типом Python

При вечернем восстановлении18.09 диагностический console-verifier был запущен через python.exe, тогда как production использует pythonw.exe. В digest вошла другая идентичность base Python; возник ложный FAIL binding. Это **VERIFIER_DEFECT**, а не новый установленный Python drift.

Проверка тем же read-only способом под production-эквивалентным pythonw.exe подтвердила прежний binding и сохранность. Код и production binding ради прохождения проверки не менялись; исходный FAIL сохранён.

Дополнительная оговорка: previous_attempt_unknown у инспектора активной записи starting без terminal нельзя считать ещё одним остановленным runtime, когда Main Running, readiness и lease одновременно PASS.

Источник: EVIDENCE.operator_recovery_relay_evening_20260918.verifier_correction; [m1-s1-preservation-20260918-evening-console-identity.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-preservation-20260918-evening-console-identity.json>); [m1-s1-preservation-20260918-evening-windowed.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-preservation-20260918-evening-windowed.json>).

### Неполнота диагностики, не отдельные падения

1. Relay stderr не сохраняется: exit255 не раскрывает первопричину двух отказов.
2. Исходные boolean readiness-пробы не сохраняют HTTP/status/elapsed/error; поздний успешный повтор не восстанавливает исходный отказ.
3. Health LastTaskResult1 не раскрывает точную отказавшую проверку.
4. RuntimeAdmissionPaused останавливал составной observer. Непроверенные поля delivery/reconciliation должны оставаться неизвестными; это не повреждение БД.
5. Во время startup исходный FAIL сохраняется отдельно от последующего PASS. Это относится к12:07 и20:02; нельзя «переписать» первый срез успешным повтором.
6. История наблюдения дискретная; полную длительность недоступности и процент uptime по этим срезам достоверно рассчитать нельзя.

Эти ограничения важны для исправлений, но не доказывают конкретную ошибку бизнес-логики, утечку данных или причину сетевого отказа.

## Наблюдение: пропуски и инструментальные сбои

Все шесть интервалов имеют класс NOT_OBSERVED_ACCEPTED_BY_OWNER. По решению владельца они входят в календарное окно, не сбрасывают его и не дают вымышленных PASS-срезов.

| ID | Интервал МСК | Длительность | Что известно |
|---|---|---|---|
| G01 | 2026-09-16 12:17:07 → 2026-09-16 13:23:54 | 66,78 мин | Подготовительная проверка heartbeat не дошла до observer; промежуточный ответ проверял настройки уведомлений, а не runtime. |
| G02 | 2026-09-17 00:42:10 → 2026-09-17 01:46:52 | 64,69 мин | Подготовительная проверка heartbeat не дошла до observer; промежуточный ответ проверял настройки уведомлений, а не runtime. |
| G03 | 2026-09-17 06:23:22 → 2026-09-17 08:16:08 | 112,75 мин | Исчерпание недельного лимита Codex — прямое сообщение владельца, не независимо восстановленная история лимитов и не отказ бота. |
| G04 | 2026-09-18 00:16:02 → 2026-09-18 02:32:38 | 136,60 мин | Два тайм-аута автоматического согласования запуска наблюдателя; observer не запускался. |
| G05 | 2026-09-18 10:32:29 → 2026-09-18 11:54:38 | 82,14 мин | Нет промежуточного завершённого среза; внутри интервала подтверждены перезапуски Windows и незапуск бота. Причина пропуска отдельно не установлена. |
| G06 | 2026-09-18 21:44:14 → 2026-09-18 22:44:18 | 60,08 мин | Нет промежуточного завершённого среза; причина UNKNOWN. Успешные граничные срезы не доказывают непрерывность. |

Источник: EVIDENCE.observation.gaps. Для G04 дополнительно: [m1-s1-observation-attempt-20260918-0127.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-attempt-20260918-0127.json>). Это два тайм-аута проверки разрешения **до запуска** observer, не отказ бота и не разрешение обходить согласование.

Отдельный существующий блокер Nobus Memory — MEMORY_OPERATION_FAILED при scoped Search, Health READY; managed update ранее не применён из-за отклонённых аргументов. Его неизменный отказ не повторялся и не блокировал независимое чтение локальных доказательств. Эти сведения о контуре наблюдения не добавлены к количеству падений продукта. Источник: EVIDENCE.nobus_memory.

После конца окна попытка удаления heartbeat была отклонена как более сильное действие, чем разрешённая приостановка. Удаление не выполнено; затем штатная приостановка PAUSED подтверждена. Это служебное событие завершения, **за пределами 72 часов**, не отказ production.

## Резервирование и сохранность данных

| Запуск МСК | Копия | Полный цикл | Учёт |
|---|---|---|---|
| 17.09 03:30:01 | Проверена, generation daily-20260917T033035-f108d31681af4818b0c7d32a5a0f1436 | complete03:32:12, LastTaskResult0 | Плановый, 1-й успех |
| 18.09 03:30:01 | Проверена, generation daily-20260918T033035-005adf9dd1ba492f83987e7cf36e2bee | failed_operator_required, LastTaskResult1; runtime не восстановлен | Плановый FAIL, не засчитан |
| 18.09 07:39 — ручное восстановление | Проверена, generation daily-20260918T073905-7f7fc943c2414c6b8bb211b33c3a7e1c | complete, recovery PASS07:40:38 | Ручной, не засчитан как плановый |
| 19.09 03:30:01 | Проверена, generation daily-20260919T033035-92d999fdeb32423abae9722fa9830349 | complete03:32:07, LastTaskResult0 | Плановый, 2-й успех |

Плановые stop/start17.09 и19.09 — ожидаемые операции backup, а не аварии. Повторяющийся Backup LastTaskResult1 после18.09 не означает новый провал в каждом последующем срезе.

В измерениях и проверках восстановления не обнаружено потери прежних строк, отката offset, повреждения четырёх БД или новых неизвестных исходов доставки. Контрольные87tasks/85receipts/16confirmed parts сохранены. Во время admission hold часть delivery/reconciliation полей не проверялась; эти интервалы не объявляются PASS.

Последний срез19.09 08:01:04: local/public PASS, Health0, все3 задания включены, один логический Core/supervisor/relay и listener8765, одна active lease; unknown delivery0, очередь пуста, reconciliation=false, offset375633520/revision64902. Это состояние на тот момент, **не новая проверка работоспособности при составлении данного журнала**.

Источники: EVIDENCE.observation.planned_backup_generations; [m1-s1-backup-journal-20260919-0337.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-backup-journal-20260919-0337.json>); [m1-s1-observation-20260919-0801.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260919-0801.json>).

## Все отрицательные срезы основного observation

Таблица включает каждый из16 срезов внутри окна с local/public FAIL, неуспешным завершённым Health либо новыми аварийными terminal-событиями. Запланированные backup stop/start исключены. Отдельные scoped повторы и ошибки verifier приведены в карточках выше. Health267009 означает выполняющееся задание, не завершённый FAIL.

| Время МСК | Local / public | Health result | Новых аварийных terminal | Квитанция |
|---|---|---:|---:|---|
| 2026-09-17 09:59:39 | PASS / FAIL | 0 | 0 | [m1-s1-observation-20260917-0959.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260917-0959.json>) |
| 2026-09-17 22:37:04 | PASS / PASS | 0 | 1 | [m1-s1-observation-20260917-2237.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260917-2237.json>) |
| 2026-09-18 03:06:08 | FAIL / FAIL | 1 | 1 | [m1-s1-observation-20260918-0306.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-0306.json>) |
| 2026-09-18 04:05:50 | FAIL / FAIL | 1 | 2 | [m1-s1-paused-backup-diagnostic-20260918-0405.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-paused-backup-diagnostic-20260918-0405.json>)<br>Исходный отказ: [m1-s1-observation-20260918-0403-failed.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-0403-failed.json>) |
| 2026-09-18 04:40:51 | FAIL / FAIL | 1 | 0 | [m1-s1-paused-backup-diagnostic-20260918-0440.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-paused-backup-diagnostic-20260918-0440.json>)<br>Исходный отказ: [m1-s1-observation-20260918-0440-failed.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-0440-failed.json>) |
| 2026-09-18 05:13:53 | FAIL / FAIL | 1 | 0 | [m1-s1-paused-backup-diagnostic-20260918-0513.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-paused-backup-diagnostic-20260918-0513.json>)<br>Исходный отказ: [m1-s1-observation-20260918-0513-failed.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-0513-failed.json>) |
| 2026-09-18 05:46:47 | FAIL / FAIL | 1 | 0 | [m1-s1-paused-backup-diagnostic-20260918-0546.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-paused-backup-diagnostic-20260918-0546.json>)<br>Исходный отказ: [m1-s1-observation-20260918-0546-failed.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-0546-failed.json>) |
| 2026-09-18 06:19:55 | FAIL / FAIL | 1 | 0 | [m1-s1-paused-backup-diagnostic-20260918-0619.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-paused-backup-diagnostic-20260918-0619.json>)<br>Исходный отказ: [m1-s1-observation-20260918-0619-failed.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-0619-failed.json>) |
| 2026-09-18 06:58:07 | FAIL / FAIL | 1 | 0 | [m1-s1-paused-backup-diagnostic-20260918-0658.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-paused-backup-diagnostic-20260918-0658.json>)<br>Исходный отказ: [m1-s1-observation-20260918-0657-failed.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-0657-failed.json>) |
| 2026-09-18 11:54:38 | FAIL / FAIL | 1 | не задано | [m1-s1-observation-20260918-1154.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-1154.json>) |
| 2026-09-18 12:07:38 | FAIL / FAIL | 1 | не задано | [m1-s1-poststart-20260918-1207.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-poststart-20260918-1207.json>) |
| 2026-09-18 17:36:13 | PASS / PASS | 1 | 0 | [m1-s1-observation-20260918-1736.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-1736.json>) |
| 2026-09-18 19:16:36 | FAIL / FAIL | 1 | 2 | [m1-s1-observation-20260918-1916.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-1916.json>) |
| 2026-09-18 19:50:48 | FAIL / FAIL | 267009 | 0 | [m1-s1-observation-20260918-1950.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-1950.json>) |
| 2026-09-18 19:57:40 | FAIL / FAIL | 1 | 0 | [m1-s1-observation-20260918-1957-before-recovery.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-1957-before-recovery.json>) |
| 2026-09-18 20:02:26 | FAIL / FAIL | 1 | 0 | [m1-s1-observation-20260918-2002-startup.json](<C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/m1-s1-observation-20260918-2002-startup.json>) |

Ряд04:05 объединяет два новых terminal03:25 и03:27. Последующие ночные строки до06:58 — продолжение того же I04. Ряд19:16 объединяет два terminal18:50 и18:51;19:50,19:57 и20:02 — продолжение I07. Ряд12:07 — startup в восстановлении I05. Поэтому сумма строк и сумма terminal отвечают на разные вопросы.

## Исторические события, не включённые в эти 72 часа

Они сохранены для контекста, но не добавлены к7 инцидентам текущего окна.

| Событие МСК | ID | Почему отдельно |
|---|---|---|
| 15.09 19:51 | PUBLIC_READINESS_20260915T165104 | Внешний probe FAIL, повтор PASS; до начала окна, причина UNKNOWN |
| 16.09 03:02 | PUBLIC_READINESS_20260916T000230 | Terminal public readiness и автоповтор; до08:00, причина UNKNOWN |
| 16.09 03:31 | BACKUP_RESTART_BLOCKED_20260916T003109 | Прежний backup restart78 из-за доказанного изменения base pythonw в кэше Codex; восстановлен, Python закреплён до окна |
| 16.09 07:23 | LOCAL_PROBE_20260916T042354 | Local probe FAIL, scoped повтор PASS; до08:00, причина UNKNOWN |

Старые дефекты maintenance-кандидатов, остановки10–13 сентября и исторические L1/L2/L3 не являются новыми багами окна16–19 сентября и не перепроверялись. Закрепление Python завершено16.09 07:55; это основание фиксированного старта08:00, а не объяснение последующих UNKNOWN-событий.

## Что осталось для пакетного исправления

Это предложения по следующему этапу в **том же M1-S1**. Код и эксплуатационная политика данным журналом не изменяются.

| Приоритет | Проблема / владелец исправления | Что требуется доказать |
|---|---|---|
| Высокий | Отсутствие автоматического восстановления после host reboot; recovery-контракт | Безопасное согласование незавершённой прежней попытки, проверка отсутствия старого runtime/lease и неизвестных effects; без blind reset, дублей и обхода evidence |
| Высокий | Relay startup/relay_start exit255 останавливает серию; диагностика и эксплуатационный контракт | Сначала установить allowlisted класс причины. Затем отдельно решить, допустим ли ограниченный retry именно для этого класса; сохранить запрет повтора UNKNOWN/permanent и требование proven cleanup |
| Высокий | Backup после аварийной серии не возвращает runtime; backup/recovery | Полный негативный сценарий: созданная копия, отклонённый restart, cleanup failure, hold и операторский выход. Целая копия не должна маскировать незавершённый цикл |
| Средний | Недостаточно диагностических данных public/relay/Health | Сохранение безопасных HTTP status, elapsed/deadline и error class; ограниченная очистка и редактирование чувствительных stderr-данных, без записи credentials/payload |
| Средний | V01/V02, идентичность диагностических средств | Регрессии на Host/точное readiness body/бюджеты и production-эквивалентную Python identity; исходные FAIL не заменять повторными PASS |
| Средний | Пропуски наблюдений и составной observer при hold | Явно разделять «не проверено», «недоступно», «данные целы»; не выводить непрерывную доступность из отдельных успешных срезов |

Срок/критерии нового окна требуют отдельного решения владельца. Восстановления уже выполнены; одноразовые operators повторять нельзя. MVP2 не разрешён автоматически.

## Проверка самого журнала

Профиль nobus-quality-loop: software-development, документный CHECKPOINT, низкий риск локальной обратимой сводки. Выполнена целевая сверка источников, а не повтор испытаний продукта:

- Все 121 основные квитанции существуют и совпадают с сохранёнными SHA256 — 121/121. Дополнительно сверены 22 квитанции исходных отказов и операторских восстановлений: расхождений хешей нет.
- Из квитанций независимо от описательных карточек извлечены уникальные terminal-события в границах окна:6 аварийных и2 плановых.
- Все7 incident ID внутри окна сопоставлены с карточками I01–I07;4 исторических ID вынесены за пределы счётчика.
- Сверены16 отрицательных срезов,6 длительных gaps, recovery checkpoints, два verifier defects и2 зачётных плановых backup.
- Проверены все 49 локальных ссылок и структура документа; прежние EVIDENCE и INCIDENT сохранены без изменений, их SHA256 приведены в начале журнала.
- Production не опрашивался и не менялся при подготовке журнала; модель/ASR и отправка сообщений боту не запускались. Новые L2/L3 и исторические210 тестов не запускались.

Это журнал выявленных фактов с ограничениями доказательств, не новый PASS релиза или квалификации.
