# Production STOP Nobus Space Bot — 20.09.2026

Статус: **восстановлен 20.09 в 13:37 МСК**. Это новый эксплуатационный инцидент после [приёмки MVP1](../gates/mvp1-maintenance/REPAIR-ACCEPTANCE.md) 19.09. Принятый LIVE-код `0c9b778ef59eb4cc01d3ab0c2ef9a14969801d83` остался неизменным. Старый план MVP2 не запускался.

## Доказательная временная линия

Все часы ниже — МСК. Источники: аутентифицированные recovery/fallback и Health-журналы, DPAPI-квитанция backup, события Windows System, readback Планировщика и штатный read-only observer. Сырые сообщения, содержимое БД и частные журналы не переносились в репозиторий.

| Время | Подтверждённый факт |
|---|---|
| 19.09, 23:05:47–23:06:06 | Health и local/public readiness были PASS. Зафиксирован `starting` здорового работающего экземпляра; terminal до остановки не появился. |
| 23:06:12–23:06:24 | Windows зарегистрировала выключение питания и переход в энергосберегающее состояние. |
| 20.09, 07:38:48 | Windows возобновилась с прежним BootIdentifier. Это не доказанная новая загрузка для автоматического согласования `starting`. |
| 07:39:26 | Первый запуск: `recovery_history_blocked`, exit 78. Он произошёл до утреннего backup. |
| 07:44:46–07:45:00 | Стартовали Backup и Health. Health: четыре БД PASS, local deadline FAIL, public HTTP 502. |
| 07:45:54 | Backup создал проверенную копию четырёх БД. |
| 07:46:39–07:46:49 | Попытка запуска Bot из backup получила тот же exit 78. |
| 07:53:22 | Подлинная квитанция: `failed_operator_required`, отказ на `starting/restart_not_ready`, копия VERIFIED, hold=true, cleanup_proven=true, runtime NOT_READY. |
| 13:20–13:27 | Read-only срез: local deadline 2 с, public 502; Bot/Health Disabled, Backup Enabled/Ready. Core, relay, listener и активной lease нет. `inspect-recovery` с таким набором заданий вернул `activation_binding_invalid` (75). |
| 13:29–13:32 | После разрешения владельца Backup временно отключён; штатный `inspect-recovery` под production pythonw подтвердил `previous_attempt_unknown` и неизменный head истории. Повторная сверка доказала отсутствие runtime и незавершённой очереди, подлинность копии/hold, логическое совпадение всех четырёх БД. |
| 13:32–13:36 | Выполнено exact-digest acknowledgement этой серии с сохранением истории; inspect стал `PASS/new`. Backup вновь включён, `recover-failure-digest` завершился `PASS/complete`, создал новую VERIFIED-копию, запустил Main и включил Health. |
| 13:37 | Main Running, Health Ready/последний результат 0, Backup Enabled/Ready. Local/public HTTP 200 с точным телом; один процессный контур Core/relay и listener, активная lease, hold отсутствует. |

## Причина и границы вывода

Подтверждённый механизм остановки — история с незавершённым `starting` при прежнем BootIdentifier. [Supervisor](../../scripts/run_nobus_space_live.py) останавливает новый запуск с кодом 78; [boot reconciliation](../../scripts/reboot_recovery.py) допускает автоматическое продолжение только при доказанной смене загрузки и чистых эффектах. Backup создал исправную копию, но не смог открыть запрет истории. HTTP 502 и отказ Health — следствия недоступности runtime в этом срезе. Точный механизм прекращения предыдущего процесса без terminal-записи неизвестен. События выключения Windows устанавливают временную связь, но не заменяют доказательство причины исчезновения процесса.

Дополнительный риск: при read-only сверке [валидатор эффектов](../../scripts/reboot_recovery.py) отклонил одну `kind=action` запись. Проверка по [схеме callback](../../src/application/durable_confirmations.py) установила подлинную owner-bound Telegram-кнопку, срок которой истёк до утренней попытки; очередь эффектов и неизвестные доставки отсутствовали. Валидатор предполагает схему исполняемой capability для всех `kind=action`. Этот пробел не вызвал утренний код 78 при неизменном BootIdentifier, но блокировал бы автоматическое согласование после реальной смены загрузки. Изменение кода вынесено в отдельную maintenance-работу с негативными регрессиями; production-код инцидента не менялся.

## Данные, восстановление и проверки

До любых действий все четыре БД в точном StateRoot из main action прошли штатную проверку и совпали с подлинной утренней копией по логическим хэшам. Утренняя копия VERIFIED, но полный цикл FAIL; эти статусы не смешивались. На момент восстановления было 88 задач, 18 подтверждённых частей доставки, `delivery_unknown=0`, пустая незавершённая очередь и `reconciliation=false`. История recovery не удалялась, БД не откатывались. Точное acknowledgement выполнено только после проверки прежнего head и безопасности эффектов.

Восстановительный backup завершился в 13:36:29 с новой VERIFIED generation `daily-20260920T133408-f3ecf5c99f1a475482e788784203a7aa`, hold снят. Независимый срез 13:37:38: четыре БД и межбазовая сверка PASS; pending/leased/unknown/failed deliveries — 0, confirmed parts — 18; offset `375633576` при активной lease (до восстановления `375633524`). Local 297 мс / public 984 мс при deadlines 2000/5000 мс, HTTP 200 и точное тело. Health по расписанию завершился с кодом 0. Процессы Bot и его дети образуют одно дерево, один reverse SSH relay и один listener 8765. Сохранённый `starting` теперь относится к работающему runtime и сам по себе не является аварией. `LastTaskResult=1` у Backup остаётся историческим результатом утреннего Scheduler-запуска; успешный восстановительный цикл подтверждается своей аутентифицированной квитанцией.

После точного разрешения владельца из его Telegram Desktop отправлена одна text-задача в 13:43. В 13:44 чат получил правильный ответ `42` и `nobus-result.txt` размером 2 байта. Новая задача в БД имеет `answered`, revision 6; число задач выросло с 88 до 89, подтверждённых частей — с 18 до 20. Её outbox `acked`, две части имеют квитанции, attempt_count 1; unknown/pending/leased/failed deliveries остаются 0. Исходное сообщение не повторялось. Это целевая проверка восстановленного production, не новая приёмка MVP1.

Контрольный read-only срез в 13:47:12–13:47:13 после доставки сохранил PASS для всех проверок observer. Local/public HTTP 200 с точным телом, 297/1141 мс; четыре БД и cross-database PASS, hold=false, lease активна, offset `375633577`; pending/leased/unknown/failed deliveries — 0, confirmed parts — 20. Новая VERIFIED-копия остаётся свежей.

Следующая работа: исправить различение callback и исполняемой effect capability в boot reconciliation, доказать сохранение STOP для незавершённого/неизвестного эффекта и callback с неверной привязкой, затем провести обычный отдельный code review/deploy с новой activation binding. Не повторять приёмку MVP1 и не запускать MVP2 из этого инцидента.
