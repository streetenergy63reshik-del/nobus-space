# M1-S1 — HANDOFF

## Действующая точка — 19.09.2026, 11:48 МСК

Ремонт опубликован PR33/34 и развёрнут: source/deployed0c9b778,
merge8af1309. L2/L3 PASS; короткая проверка runtime, два Health, полный controlled
backup и сохранность четырёх БД PASS. Подробная таблица и доказательства —
[REPAIR-ACCEPTANCE.md](REPAIR-ACCEPTANCE.md) и
`EVIDENCE.post_window_repair_20260919`.

M1-S1 OPEN: одна text/TXT квалификация НЕ выполнена. Реальных модельных/ASR
вызовов в ремонте0. Ожидается ответ на уже заданный вопрос о лимите модели:
один исполнитель плюс штатный semantic-разбор или строго один вызов суммарно.
Не отправлять задачу и не обходить admission до ответа. Все операторы
переключения/backup уже использованы; их и прежние проверки не повторять.
Runtime работает независимо от чата. Историческое окно NOT PASS, heartbeat
PAUSED, MVP2 не запущен. Ниже — сохранённая история передачи.

## Решение владельца и начало ремонта — история

Владелец в этой же задаче разрешил полный пакет ремонта, независимую проверку,
штатные commit/push/PR/merge и production-переключение с короткой приёмкой.
Предыдущее ограничение «только read-only» заменено этим решением. Новое окно
72 часа не требуется. Историческое окно остаётся NOT PASS, heartbeat PAUSED,
MVP2 запрещён. Пока итоговый кандидат не принят и live-проверка не завершена,
M1-S1 OPEN и MVP1 ещё не имеет окончательной эксплуатационной приёмки.

Актуальные изменения, таблица I01–I07/V01–V02, критерии, путь возврата и
доказательства: [REPAIR-ACCEPTANCE.md](REPAIR-ACCEPTANCE.md).
Ниже сохранена передача до нового решения владельца; её разрешения и следующий
шаг больше не управляют текущим ремонтом.

## Актуальная передача в следующий чат — 19.09.2026, 10:05 МСК

Это действующая сводка для передачи текущей работы по прямому запросу владельца. Раздел «Исторические checkpoints» ниже сохраняет прежние записи, но старые указания ACTIVE, «продолжать до 08:00», «backup 1/2» и предыдущие начала окон больше не описывают текущее состояние.

**Главное:** фиксированное 72-часовое окно завершено. Бот был работоспособен в последнем срезе, но устойчивость **NOT PASS**. Gate **M1-S1 OPEN**, **M2-G0 BLOCKED**. Heartbeat **PAUSED**. Новый чат принимает продолжение этого же Gate, а не открывает второй параллельный M1-S1. C6 не переоткрывать, MVP2 не запускать.

### 1. Задача и границы передачи

В этом чате сопровождали maintenance-кандидат MVP1, его принятие, запуск, квалификацию реальной задачей, закрепление production Python и 72-часовое наблюдение. По отдельным прямым поручениям владельца выполнялись ограниченные восстановления бота; причины и исходные отказы сохранены. Затем подведён итог окна и собран полный журнал инцидентов. Последний запрос — подготовить handoff и короткий промпт, **не исправлять код и не запускать новое наблюдение**.

Разрешённый старт нового чата: восстановить контекст, проверить локальные доказательства и несвязанные изменения, подготовить пакетный план исправлений для согласования. Предложения из журнала ещё не означают разрешения на реализацию, deploy, изменение recovery-политики или новое окно.

### 2. Карта рабочих каталогов

| Назначение | Точный путь |
|---|---|
| Canonical repository | C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev |
| Рабочее дерево этого Gate | C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/worktrees/m1-s1-stability |
| Пакет M1-S1 | C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/worktrees/m1-s1-stability/docs/gates/mvp1-maintenance |
| LIVE checkout | C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/worktrees/telegram-live |
| Production state | C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/production-c6/migration-01/state |
| Production backups | C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/production-c6/backups |
| Квитанции наблюдения и восстановления | C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime |
| Закреплённый base Python | C:/Хранилище/АГЕНТ/PROстранство/ОРКЕСТРАТОР/Code/nobus-orchestrator-dev/.runtime/production-python/cpython-3.12.14-ed91bed4/base |

Рабочая ветка — **codex/m1-s1-stability**, фактический HEAD при передаче — **0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c**. Это существующее дерево; не создавать новый worktree и не переносить LIVE по умолчанию.

### 3. Что читать и в каком порядке

1. Применимые AGENTS.md, затем [docs/README](../../README.md) для иерархии источников.
2. Эту актуальную сводку полностью и [CURRENT-STATUS](../../handoffs/CURRENT-STATUS.md).
3. [JOURNAL-72H.md](JOURNAL-72H.md) — полный журнал семи инцидентов, ошибок диагностики, пропусков, причин и предложений для исправлений.
4. [EVIDENCE.json](EVIDENCE.json): publication_checkpoint, observation.final_verdict, observation.samples/incidents/gaps/planned_backup_generations, operator_recovery_20260918, operator_restart_after_reboot_20260918, operator_recovery_relay_evening_20260918, python_pinning_20260916, qualification_checkpoint.
5. [INCIDENT-20260918.md](INCIDENT-20260918.md) и конкретные связанные квитанции — только для разбора соответствующего эпизода.

Не загружать весь старый чат, сырые production-журналы, секреты или все исторические окна. Git revision и привязанные доказательства имеют приоритет над старой повествовательной строкой. Старые значения EVIDENCE вне observation.final_verdict могут описывать прежний checkpoint; не подменять ими финальный итог.

### 4. Принятый код и исторические PASS

| Слой | Принятый результат |
|---|---|
| Опубликованный release | v1.0.2, commit82003c03d8a36015703472b472640ab4021fb416, тег не перемещён |
| Maintenance source/deployed | 0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c |
| Merge/main | 26860adfeae84fa075a8f3cb3260e9d4c6dd9257, принят через PR32 |
| Source tree | fd9b3f5e78fecf453e6ad28bf663d4a1797486c3 |
| Кандидат | Исторические L1/L2/L3 PASS и 210 PASS сохранены |
| Реальный Scheduler fixture | PASS; bounded recovery, budget/permanent stop и cleanup доказаны для принятого снимка |
| Реальная квалификация | Одна исполненная задача, text/TXT доставлены и проверены, один worker attempt; ASR0 |

Freeze SHA256: **43ca0132251542f0f3dd3de7d4cd55d46b145decb5066d5f4a9779d01b18adcd**.
Review SHA256: **f128ffc6014ac4ecd5c38acf0b8659dfca3bdb2c09eb80126abd583f3efc730c**.
Реальный Scheduler result SHA256: **92c5df173abd2d52a510f8db7750047dcf958c01e8a01363c65ff5fb6607ad19**.

Только смена чата не является основанием повторять эти проверки, новую реальную задачу, модельный вызов, ASR или отправку боту. После будущего изменения кода объём повторных проверок определяется затронутыми контрактами и новым замороженным снимком, а не автоматически переносится со старого PASS.

### 5. Production environment и binding

16.09 в07:55 МСК завершён environment-only переход: canonical .venv использует закреплённый base Python3.12.14 из собственного production-python, а не обновляемый кэш Codex. Код,80 пакетов, config и Scheduler Actions сохранены; backup/start и сохранность прошли проверку.

Activation binding: **sha256:0c2b23037184c41a2dac3d6b94df38e5fa6f5103e25303438be46e8fc4af2c5b**.
Backup config digest: **sha256:9c92ef673c03d77a97fefa1bd023091d37ac03f908739833b614208ca8caa645**.

Доказанный Python drift до начала окна исправлен закреплением среды. Причины последующих SSH/public сбоев этим **не объяснены**. Проверка binding требует production-эквивалентной identity pythonw.exe: использование console python.exe уже давало ложный диагностический FAIL.

### 6. Окно и окончательные критерии

Окно неизменно: **16.09.2026 08:00 → 19.09.2026 08:00 МСК**, UTC **2026-09-16T05:00:00Z → 2026-09-19T05:00:00Z**.

Владелец уточнил старт после закрепления Python и отдельно отменил сброс/приостановку отсчёта из-за промежутков без измерений. Такие интервалы отмечены NOT_OBSERVED_ACCEPTED_BY_OWNER: они входят в календарное время, но не доказывают доступность. Реальные остановки и простой не исключены из истории и не превращены в успешную работу. Только пропуск17.09 06:23–08:16 объяснён владельцем исчерпанием недельных лимитов Codex; на другие пропуски это объяснение не переносится.

Заключительное измерение — **19.09 08:01:04.559878 МСК**, после дедлайна на64,56с. Оно не подменяет измерение ровно в08:00, не продлевает окно и не подтверждает непрерывную доступность.

| Вердикт | Итог |
|---|---|
| release | v1.0.2 без изменений |
| candidate | Прежний принятый PASS для0bd63db / merge26860ad |
| runtime | PASS только на момент последнего среза08:01 |
| qualification | Прежний PASS реальной задачи/text/TXT; не повторён |
| stability | **NOT PASS** |
| M1-S1 | **OPEN** |
| M2-G0 | **BLOCKED** |

72 календарных часа прошли, два плановых backup подтверждены. Однако серия перезагрузок ПК нарушает доказательство72ч непрерывно включённого ПК; были реальные остановки и ручные восстановления, первопричины ряда отказов UNKNOWN. Полнота наблюдения ограничена. Новый срок/окно самостоятельно не назначать.

### 7. Последнее подтверждённое состояние бота

Это срез **19.09 08:01 МСК**, а не новая live-проверка в момент подготовки handoff:

- Local/public readiness PASS.
- Все3 задания включены: NobusSpaceBot — Running; NobusSpaceBot-Health — Ready/0, LastRun08:00:43; NobusSpaceBot-Backup — Ready/0, LastRun03:30:01.
- Одна логическая цепочка Core/supervisor/relay, listener8765 и одна active polling lease. Venv wrapper и base interpreter считаются одной цепочкой, а не двумя экземплярами.
- Четыре БД PASS:87tasks/87ingress/170audit/85messages/85receipts/8sealed answers/16confirmed parts. Эти числа — baseline, не потолок пользовательских задач.
- Очередь пуста, delivery pending/leased/unknown/failed=0, reconciliation=false.
- Offset375633520, checkpoint revision64902; offset и принятые данные не уменьшились.
- Последний recovery attempt1, budget10; admission hold отсутствует. После среза07:25 новых terminal/fallback events и изменения цепочки процессов не обнаружено.

Квитанция: canonical/.runtime/m1-s1-observation-20260919-0801.json.
SHA256: **d18ab8e6aa7b041b29f4e62ee98a0239f92993448abb6338bf0cb750cc8eab70**.
Authenticated history tail: **sha256:4aed631769b0d00669d6549b966a87eed5aef5b75d61cf64c13fd1237081e565**.

### 8. Резервные копии: фактический зачёт

| Запуск | Generation | Результат / учёт |
|---|---|---|
| 17.09 03:30 МСК | daily-20260917T033035-f108d31681af4818b0c7d32a5a0f1436 | Плановый полный цикл PASS,1-й зачёт |
| 18.09 03:30 МСК | daily-20260918T033035-005adf9dd1ba492f83987e7cf36e2bee | Целая копия, но restart FAIL/78 и hold; **не засчитан** |
| 18.09 07:39 МСК | daily-20260918T073905-7f7fc943c2414c6b8bb211b33c3a7e1c | Ручной recovery complete; **не плановый** |
| 19.09 03:30 МСК | daily-20260919T033035-92d999fdeb32423abae9722fa9830349 | Плановый полный цикл PASS,2-й зачёт |

Для19.09: LastRunTime03:30:01, LastTaskResult0; protected journal complete03:32:07.076685, длительность126,077с. Planned stop03:30:27, cleanup proven, starting03:31:10. Копия authentication/binding/ciphertext/freshness PASS.
Journal receipt: canonical/.runtime/m1-s1-backup-journal-20260919-0337.json, SHA256 **d06d12eaf06903b028232ce5f8692c4357fbff66370fd531645daf4516cddeb5**.
Последний NextRunTime был20.09 03:30 МСК — вне завершённого окна, не обещание будущего успеха.

### 9. Инциденты и доказанные ограничения

Полные карточки, времена, квитанции и SHA-привязки — в JOURNAL-72H. Сводка:

| ID журнала | Событие | Статус причины |
|---|---|---|
| I01 | 17.09 09:59 public probe FAIL; local и процессы в норме, повтор10:01 PASS | Причина UNKNOWN, остановка runtime не доказана |
| I02 | 17.09 22:31 public_readiness_failed, attempt1; автоповтор и PASS22:37 | Механизм retry доказан, первопричина UNKNOWN |
| I03 | 18.09 03:04 public_readiness_failed, attempt2→3;03:06 обе readiness FAIL | Полное промежуточное восстановление не доказано |
| I04 | 18.09 03:25 public отказ,03:27 relay_exit255 на startup attempt4; backup restart78, cleanup70, hold | STOP до исчерпания бюджета; SSH причина UNKNOWN; восстановлен07:40 |
| I05 | 18.09 11:11–11:14 перезапуски Windows; Main был вызван, но78/previous_attempt_unknown | Причина блокировки доказана, инициатор/причина reboot UNKNOWN; восстановлен12:08 |
| I06 | 18.09 17:35 Health1 при доступном боте; следующий Health0 | Причина UNKNOWN, падение Core не доказано |
| I07 | 18.09 18:50 public отказ;18:51 relay_exit255 на relay_start attempt2/10, stop_non_retryable | SSH причина UNKNOWN; восстановлен20:04 |

Внутри окна6 уникальных аварийных terminal-событий supervisor и отдельная серия host reboots. Это не7 независимых простоев: I03/I04 связаны ночной серией; повторные отрицательные срезы одной остановки не считаются новыми падениями.

Два verifier defects: **V01** — scoped local probe без обязательного Host получил400; **V02** — console python.exe вместо production pythonw.exe дал ложный binding FAIL. Исходные результаты сохранены; это не доказанные новые баги production.

Значимые ограничения: stderr relay не сохранён (DEVNULL), boolean probe не раскрывает исходный HTTP/error, Health1 не раскрывает отказавшую проверку. Во время admission hold составной observer прерывался с RuntimeAdmissionPaused; это не доказательство повреждения БД, а непроверенные delivery/reconciliation нельзя заменять нулями. Точный downtime/uptime-процент из дискретных срезов не вычисляется.

### 10. Выполненные восстановления и исчерпанное разрешение

18.09 по трём отдельным прямым поручениям владельца выполнены точные acknowledgement/start/recover действия. Перед ними проверялись сохранность, исходы предыдущих действий и необходимые разрешения; исходные отказы не удалялись.

- Утро: оператор m1-s1-recover-20260918.py,8 изолированных тестов; acknowledgement07:37:18 и recover-failure PASS07:40:38; независимый readback07:41:56.
- После reboot: m1-s1-restart-after-reboot-20260918-*.json,6 изолированных тестов; acknowledgement12:05, один Start12:06:35; первоначальный FAIL12:07 сохранён; PASS12:08.
- Вечер: m1-s1-restart-after-relay-20260918-evening.py,8 изолированных тестов; acknowledgement20:00, один Start20:01:35; первоначальный FAIL20:02:26 сохранён, scoped PASS20:02:53, независимый PASS20:04:35.

Имена приведены для поиска evidence, **не как команды к повторному исполнению**. Все одноразовые разрешения использованы. Старые repair/pin/transition/recovery operators нельзя запускать вновь. Новое восстановление production требует нового точного поручения и проверки неизвестных effects до повтора. Отката БД, изменения продуктового кода/config/Scheduler Actions в этих восстановлениях не выполнялось.

### 11. Heartbeat и передача владения

Автоматизация **m1-s1-mvp1**, имя «M1-S1 — наблюдение стабильности MVP1», тип heartbeat, прежний интервал30мин. **PAUSED** подтверждён штатным automation_update и повторным чтением метаданных при подготовке этой передачи19.09 10:05 МСК.

Она привязана к исходной задаче **01a09c25-1d78-73e2-8691-be3db59a9fd1**. Не создавать дубликат и не переносить/возобновлять её автоматически из нового чата. Новое окно, расписание и целевая задача требуют отдельного решения владельца. Попытка удаления была отклонена; удаления не было, приостановка выполнена. Остановка наблюдения не останавливает самого бота и его Scheduler задачи.

Этот handoff и промпт подготовлены для ручного запуска владельцем нового чата; новая задача средствами Codex в ходе подготовки не создавалась. Прежний чат не должен параллельно начинать тот же пакет исправлений.

### 12. Рабочие файлы и что нельзя потерять

Последние запросы создали JOURNAL-72H.md и добавили указатели в HANDOFF/CURRENT. EVIDENCE и INCIDENT при составлении журнала не изменялись. Документация остаётся локальным WIP, **без commit/push**.

На момент передачи git status содержит изменённые:
docs/01-Единый-документ-проекта.md; docs/08-Runbook-эксплуатации.md; docs/README.md; docs/gates/README.md; docs/gates/mvp1-maintenance/EVIDENCE.json; docs/gates/mvp1-maintenance/HANDOFF.md; docs/handoffs/CURRENT-STATUS.md; docs/handoffs/WORKSPACE-INVENTORY.md.
Новые, ещё не отслеживаемые Git файлы: docs/gates/mvp1-maintenance/INCIDENT-20260918.md и JOURNAL-72H.md.

Не откатывать, не чистить дерево и не считать эти изменения своими. Перед последующей правкой сверить фактический status и точную область изменений. Квитанции canonical/.runtime также локальные; наличие Git commit само по себе не гарантирует их перенос на другой компьютер. Не переносить private runtime/state в другой контур без отдельного разрешения.

### 13. Read-only инструменты для будущей диагностики

Для восстановления контекста новый live-прогон не нужен. Если последующая согласованная задача требует актуального среза, штатная команда запускается **из canonical**, не из stability worktree:

```powershell
.venv\Scripts\python.exe .runtime\m1-s1-observe-readonly.py
```

Перед каждым запуском проверить SHA256 helper:
**c6508cbbbfc466cac523661733ca4827e8588688789ff457e81e466d8b4d7e06**.
Файл и этот hash сверены при подготовке передачи, но observer повторно не запускался. Для DPAPI/Scheduler может требоваться штатный require_escalated под Windows identity владельца. Отказ не обходить; неизвестный исход сначала сверить.

Наблюдатель не перезапускает сервисы и не пишет production. При readiness FAIL исходный результат сохраняется; один scoped диагностический повтор может уточнить HTTP/status/elapsed/deadline/error, но не отменяет FAIL. Не выводить payload, строки задач, argv/env, credentials. Не читать приватные каталоги рекурсивно.

Известные ловушки инструментов:
- PowerShell ConvertFrom-Json -DateKind String сохраняет точные ISO timestamps; автоматическое преобразование дат меняет формат/дробные секунды.
- Wrapper+base — одна логическая цепочка.
- Inspector previous_attempt_unknown для текущей active starting-записи сам по себе не доказывает остановку при Main Running/readiness/lease PASS.
- Проверку activation binding нельзя подменять запуском через другую Python identity.
- Local diagnostic требует Host app.nobusspace.com и прежнего точного readiness-контракта.
- Успешные новые пользовательские задачи могут увеличивать counts/offset; baseline не потолок.

### 14. Nobus Memory и правила качества

Разрешён только scope **project:nobus-space**. Ранее контекст прочитан; последующий Search дал MEMORY_OPERATION_FAILED, однократный Health — READY; изменённый scoped Search тоже не прошёл. Managed update не применён: аргументы отклонены. Это не доказательство «Obsidian закрыт». В текущем чате неизменный отказ не повторяется и не блокирует локальные read-only доказательства; неподдерживаемый fallback запрещён.

В новом чате при неизвестной доступности использовать штатные scoped MCP-правила, не объявлять старый отказ свежим фактом. Внешняя запись в память не выполнена при подготовке handoff; канон — Git/source evidence, не память.

Для этой передачи применены правила nobus-memory и nobus-quality-loop: software-development, документный CHECKPOINT, низкий риск, точечная сверка ссылок, статусов и hash. Полный L1/L2/L3 не повторён, новый release/candidate не объявлен. Прошлая сверка журнала уже доказала121/121 hash основных квитанций,22 дополнительных квитанции и49 ссылок; она не запускается заново лишь из-за передачи контекста.

### 15. Первый следующий шаг — без реализации

1. Прочитать актуальную передачу и JOURNAL-72H; восстановить семь карточек и отделить доказанные механизмы от UNKNOWN.
2. Read-only сопоставить затронутые участки source0bd63db: relay diagnostics/retry classification, recovery после незавершённой попытки, backup restart/hold, Health и verifier identity.
3. Предложить владельцу единый пакет исправлений: цель, конкретные файлы/контракты, риски, негативные регрессии, порядок проверки и публикации. Основные направления — безопасное восстановление после reboot, диагностируемые relay/public/Health отказы, корректность backup/recovery и verifier.
4. Явно разделить исправление дефекта реализации, изменение эксплуатационного контракта и улучшение диагностики. Не ослаблять fail-closed, trust boundary, tenant isolation, идемпотентность, evidence binding, cleanup и ограничения retry ради PASS.
5. Получить решение владельца перед реализацией/production-действиями. Новое наблюдение, его начало и критерии — отдельное решение. M1-S1 остаётся OPEN до применимой приёмки; MVP2 не разрешён.

### 16. Контрольные суммы и завершение передачи

| Файл | SHA256 на момент передачи |
|---|---|
| EVIDENCE.json | 9c2f18c891577e7dc3e3e4cf3aad04cd45f8b753bc719342dbe237ce139e78a4 |
| JOURNAL-72H.md | a863691fc1b7a25f592d61c3caa8ce3bc6bb2a05baa2dcb392273594bb4889c5 |
| INCIDENT-20260918.md | 368ddd27c57f9b195db3600b7627bc4839a3feb8f07ceb63bcd29b24da8ad20f |
| Заключительная квитанция08:01 | d18ab8e6aa7b041b29f4e62ee98a0239f92993448abb6338bf0cb750cc8eab70 |

Нет активной операции восстановления, незавершённого разрешённого deploy или ожидающего исполнения operator в этой передаче. Нерешённые вопросы — первопричины перечисленных отказов, согласование пакета исправлений и будущая приёмка. Последняя доступность подтверждена08:01, а подготовка handoff10:05 не является новым runtime PASS.

---
## Исторические checkpoints — не текущие инструкции


Сводка по запросу владельца: [полный журнал инцидентов окна 16–19 сентября](JOURNAL-72H.md). Семь инцидентов, исходные отказы, две ошибки диагностики и ограничения наблюдения собраны без изменения итогового verdict.

**19 сентября, 08:01 МСК — фиксированное окно завершено: stability NOT PASS.** Окно 16.09 08:00 → 19.09 08:00 МСК составило ровно 72 календарных часа; срок не переносился, новое окно не открыто. Заключительное измерение выполнено в 08:01:04, то есть после границы окна, и не подменяет измерение ровно в 08:00. Бот работает: local/public PASS, Health Ready/0, все три задания включены, одна логическая цепочка Core/supervisor/relay, listener8765 и одна active lease. Четыре БД PASS; 87 tasks / 85 receipts / 16 confirmed parts, unknown=0, очередь пуста, reconciliation=false; offset375633520, revision64902. С предыдущего среза07:25 новых runtime exits/fallback events и изменений цепочки процессов нет. Резервные копии проверены; зачтены два плановых полных цикла17.09 и19.09 (2/2), последний Scheduler LastRunTime19.09 03:30:01, LastTaskResult0, journal complete03:32:07. Провал планового цикла18.09 и ручные восстановления не скрыты и не засчитаны как плановые успехи.

**Раздельный итог:** release v1.0.2 — без изменений; candidate 0bd63db / merge26860ad — прежний принятый PASS; runtime — PASS только на момент заключительного среза; qualification реальной задачи/text/TXT — прежний PASS, без повторных вызовов; stability — NOT PASS; M1-S1 OPEN, M2-G0 BLOCKED. Основания NOT PASS: подтверждённая перезагрузка ПК18.09 не позволяет подтвердить72ч непрерывно включённого ПК; реальные остановки public/relay и recovery_history_blocked требовали восстановления, их первопричины остаются UNKNOWN. Подтверждены relay_exit255 на startup/relay_start и stop_non_retryable до исчерпания бюджета; stderr relay не сохранён. Python drift для этих событий не установлен. Пропуски NOT_OBSERVED_ACCEPTED_BY_OWNER учитываются во времени по решению владельца, но не доказывают доступность; исходные FAIL и простой сохранены в EVIDENCE/INCIDENT-20260918.md.

Heartbeat `m1-s1-mvp1` приостановлен штатным automation_update, PAUSED подтверждён чтением TOML; удаление отклонено проверкой безопасности и не выполнено. Бот и его Scheduler задания не остановлены и не изменены. Production в этом запуске только читался; квитанция `canonical/.runtime/m1-s1-observation-20260919-0801.json`, SHA256 `d18ab8e6aa7b041b29f4e62ee98a0239f92993448abb6338bf0cb750cc8eab70`; итог в EVIDENCE.observation.final_verdict. Применена точечная проверка nobus-quality-loop; прежние 210 PASS и L1/L2/L3 не повторялись. Неизменный отказ Nobus Memory не повторялся и не блокировал локальные доказательства. Следующий шаг — согласовать пакет исправлений диагностики relay и recovery после перезагрузки в том же Gate M1-S1. Новое окно и его критерии — только отдельным решением владельца; MVP2 автоматически не разрешён. Ниже исторические checkpoints.

**19 сентября, 03:37 МСК — второй успешный плановый backup подтверждён, в зачёте 2/2.** Scheduler: LastRunTime19.09 03:30:01, LastTaskResult0; защищённый журнал complete03:32:07 привязан к generation `daily-20260919T033035-92d999fdeb32423abae9722fa9830349` и прежнему config digest9c92ef67. Цикл завершился за126,077с от запуска: planned_stop03:30:27, cleanup proven, новый runtime starting03:31:10. Проверены authentication/binding/ciphertext/freshness копии, admission hold отсутствует. Независимый read-only срез03:37:39: local/publicPASS, Health0, все3 задания включены; одна логическая цепочка Core/supervisor/relay, listener8765 и active lease. Четыре БД PASS, 87tasks/85receipts/16confirmed parts, unknown0, очередь пуста, reconciliation=false; offset375633519 не уменьшился, revision63861. Новых внеплановых остановок и fallback events с предыдущего среза нет; смена процессов соответствует плановому backup. Квитанции и второй зачётный цикл сохранены в EVIDENCE.observation. Production наблюдатель не менял, прежние остановки18.09 и неизвестные первопричины сохранены; этот успешный цикл их не отменяет. Прошло67ч37мин фиксированного окна16.09 08:00→19.09 08:00МСК; это не доказательство непрерывной работы, интервалы без наблюдения и простой не скрыты. До срока остаётся4ч22мин; heartbeat ACTIVE, только read-only. В08:00 оценить фактические критерии, без переноса срока и нового окна. M1-S1 OPEN, stability NOT PASS, M2-G0 BLOCKED. Ниже исторические checkpoints.

**18 сентября, 20:04 МСК — бот восстановлен по новому прямому поручению владельца.** Причина прекращения автоповторов подтверждена: после public_readiness_failed18:50:44 повторная попытка2 завершилась relay_exit255 на relay_start18:51:46; действующая политика классифицировала её stop_non_retryable, cleanup proven, control_closed. Бюджет10 не исчерпан. Первопричина SSH/public сбоя UNKNOWN: stderr дочернего relay не сохраняется (DEVNULL); Python drift не установлен. Новый одноразовый оператор прошёл8 изолированных тестов, проверил4БД/копию/отсутствие незавершённых effects, сохранил архив входов и выполнил штатное exact acknowledgement head374eacfa→resetc99cc608 в20:00; Main запущен один раз в20:01:35. Исходный post-start срез20:02:26 local/publicFAIL сохранён; один scoped повтор20:02:53 дал HTTP200, local281/public1109мс при deadline2000/5000. Независимый срез20:04:35: local/publicPASS, Health0, все3 задания включены, один логический Core/supervisor/relay/listener и active lease; offset375633519/revision62073. Все прежние строки сохранены: 87tasks/85receipts/16confirmed parts, unknown0, очередь пуста, reconciliation=false. Binding0c2b2303, source/config/Scheduler signatures неизменны. Дополнительный console-verifier первоначально дал FAIL из-за python.exe вместо production pythonw.exe в base identity; исходный результат сохранён как VERIFIER_DEFECT, исправленный read-only запуск под pythonw подтвердил binding и preservationPASS. БД не откатывались, code/config не менялись, новая backup не создавалась; ручная копия07:39 проверена, плановых успешных циклов1/2, Backup1 — прежний провал18.09 03:30. См. EVIDENCE.operator_recovery_relay_evening_20260918 и связанный инцидент RELAY_NON_RETRYABLE_STOP_20260918T155146: восстановлен, отрицательное evidence сохранено для пакетного исправления. Разрешение использовано, одноразовые операторы не повторять; heartbeat снова только read-only. Окно16.09 08:00→19.09 08:00МСК не прерывается и не сбрасывается; простой не считается успешной работой. M1-S1 OPEN, stability NOT PASS, M2-G0 BLOCKED. Ниже исторические checkpoints.

**18 сентября, 19:16–19:17 МСК — бот остановлен, новый инцидент.** После успешного среза18:44 authenticated history зафиксировала public_readiness_failed в18:50:44 на попытке1, cleanup proven и ожидание60с; попытка2 в18:51:46 завершилась relay_exit255 на relay_start, stop_non_retryable и control_closed. Бюджет10 не исчерпан. Первопричина SSH/public сбоя UNKNOWN; Python drift не установлен. В19:16 local/publicFAIL, процессов Core/supervisor/relay и listener8765 нет, lease неактивна; MainReady1/HealthReady1, все3 задания включены. Единственный scoped повтор19:17: local DEADLINE_EXCEEDED2016мс при deadline2000, publicHTTP502/1125мс при deadline5000; исходный FAIL сохранён. Четыре БД PASS, 87tasks/85receipts/16confirmed parts, unknown0, очередь пуста, reconciliation=false; offset375633519/revision62064. Ручная копия07:39 проверена, journalcomplete, плановых циклов1/2; Backup1 относится к прежнему провалу18.09 03:30. Инцидент RELAY_NON_RETRYABLE_STOP_20260918T155146 и квитанции canonical `.runtime/m1-s1-observation-20260918-1916.json`, `.runtime/m1-s1-stop-diagnostic-20260918-1917.json` сохранены в EVIDENCE для пакетного исправления. Production не менялся; для отдельного штатного восстановления нужно новое точное разрешение владельца, одноразовые операторы не повторять. Наблюдение продолжается только read-only, окно16.09 08:00→19.09 08:00МСК неизменно; остановка не считается успешной работой. M1-S1 OPEN, stability NOT PASS, M2-G0 BLOCKED. Ниже исторические checkpoints.

**18 сентября, 17:36–17:37 МСК — новый сбой задания Health, бот доступен.** В исходном срезе Health Ready/LastTaskResult=1 после планового запуска17:35:43; local/public=true, четыре БД PASS, один логический Core/supervisor/relay и active lease, процессы и authenticated history/fallback без новых остановок. Следующий плановый Health17:36:43 завершился0 (readback17:37:00); один scoped диагностический срез17:36:58: local/publicHTTP200,219/844мс при бюджетах2000/5000мс. Причина исходного Health1 UNKNOWN; новый успешный срез не отменяет исходный отказ. Инцидент HEALTH_TASK_FAILURE_20260918T143543 и квитанции canonical `.runtime/m1-s1-observation-20260918-1736.json`, `.runtime/m1-s1-health-diagnostic-20260918-1737.json` сохранены в EVIDENCE для пакетного исправления. 87tasks/85receipts/16confirmed parts, unknown0, очередь пуста, reconciliation=false, offset375633519/revision61767; ручная копия07:39 проверена, complete journal, плановых циклов1/2; Backup1 — прежний провал18.09 03:30. Production не менялся; разрешение на восстановление использовано, повторять операторы нельзя. Окно16.09 08:00→19.09 08:00МСК не сбрасывается, прежние отказы сохраняются. M1-S1 OPEN, stability NOT PASS, M2-G0 BLOCKED. Ниже исторические checkpoints.

**18 сентября, 12:08 МСК — бот запущен по новому прямому разрешению владельца.** После перезагрузок ПК автоматическое восстановление НЕ состоялось: Scheduler вызвал Main в11:16:14, но запуск завершился recovery_history_blocked/78, поскольку прежняя попытка осталась без terminal (previous_attempt_unknown). Это отдельный зафиксированный отказ автоматического восстановления, не отсутствие срабатывания задания. В12:05 выполнено штатное exact-digest acknowledgement head62ecf459→reset21052fd6 с сохранением истории и архивом входов; в12:06:35 существующее задание Main запущено один раз. Исходный срез12:07 local/publicFAIL во время запуска сохранён; диагностический срез12:08:03 дал local/publicHTTP200 (359/828мс, бюджеты2000/5000мс). В12:08:48 Health0, все3 задания включены, MainRunning; один логический supervisor/Core/relay и listener, одна active lease. Сохранность всех прежних строк PASS: 87tasks/85receipts/16confirmed parts, unknown0, очередь пуста, reconciliation=false, offset375633507/revision60463. Source/config/SchedulerActions/binding неизменны; БД не откатывались, новая backup не создавалась, прежняя ручная копия проверена, плановых успешных циклов1/2. Квитанции и6 изолированных тестов одноразового оператора связаны в EVIDENCE.operator_restart_after_reboot_20260918. Разрешение использовано, оператор повторно не запускать; heartbeat снова только read-only. Владелец отдельно подтвердил: автоматический незапуск после перезагрузки и все падения фиксировать в журнале для последующего пакетного исправления; общий срок НЕ сбрасывать, плановое завершение19.09 08:00МСК сохранить. Это не признание простоев успешной работой и не разрешение менять код сейчас. M1-S1 OPEN, stability NOT PASS, M2-G0 BLOCKED. Ниже исторические checkpoints.

**18 сентября, 11:54–11:56 МСК — новая остановка после перезапусков Windows.** Исходный read-only срез: local/public FAIL, процессов и listener8765 нет, lease неактивна. Windows System содержит события перезапуска/остановки/загрузки 11:11–11:14; последняя загрузка 11:14:28. Main запущен 11:16:14 и завершился recovery_history_blocked/78; authenticated fallback 11:16:56. Штатное чтение recovery-state: blocked/previous_attempt_unknown; история осталась на starting попытки1 без terminal. Инициатор и первопричина перезапусков Windows не установлены; это не доказанное повторение SSH-сбоя и не Python drift. Один диагностический повтор: local deadline2000мс, public HTTP502/515мс при deadline5000мс; исходный FAIL сохранён. Четыре БД PASS, 87tasks/85receipts/16confirmed parts сохранены, unknown0, очередь пуста, reconciliation=false, offset375633507/revision60456. Ручная копия07:39 проверена, journalcomplete; плановых успешных циклов1/2, следующий19.09 03:30. Все3 задания включены, Main78/Health1; Backup1 относится к ночному проваленному циклу. Промежуток10:32–11:54 без измерений учтён как NOT_OBSERVED_ACCEPTED_BY_OWNER с отдельным отрицательным evidence остановки. Квитанции canonical `.runtime/m1-s1-observation-20260918-1154.json` и `.runtime/m1-s1-stop-diagnostic-20260918-1156.json`; инцидент HOST_REBOOT_RECOVERY_BLOCKED_20260918T081656 в EVIDENCE. Production не менялся; прежнее разрешение на восстановление использовано утром, требуется новое точное разрешение. Окно16.09 08:00→19.09 08:00МСК неизменно. M1-S1 OPEN, stability NOT PASS, M2-G0 BLOCKED. Ниже исторические checkpoints.

**18 сентября, 07:41 МСК — бот восстановлен по прямому поручению владельца.** Штатные exact-digest acknowledgement и recover-failure завершены; независимый read-only срез: local/public PASS, один логический supervisor/Core/relay, один listener8765 и одна active lease. Четыре БД и все прежние строки сохранены: 87tasks/85receipts/16confirmed parts; unknown delivery=0, очередь пуста, reconciliation=false, offset375633507. Новая ручная generation `daily-20260918T073905-7f7fc943c2414c6b8bb211b33c3a7e1c` и complete cycle PASS, но в зачёте по-прежнему 1 успешный ПЛАНОВЫЙ backup; следующий19.09 03:30МСК. Исторический LastTaskResult1 от18.09 03:30 остаётся фактом, ручной цикл его не переименовывает. Доказанная причина блокировки: relay_exit255 на startup попытки4/10 → stop_non_retryable → backup restart recovery_history_blocked/78 → защитная пауза. Первопричина выхода SSH UNKNOWN, stderr не сохранён; Python drift не установлен. [Журнал инцидента](INCIDENT-20260918.md) и `operator_recovery_20260918` в EVIDENCE фиксируют точные квитанции и ограничение. Code/source0bd63db, merge/main26860ad, releasev1.0.2, config/Actions и activation binding0c2b2303 неизменны; БД не откатывались, history не удалялась. Владелец подтвердил: окно16.09 08:00→19.09 08:00МСК НЕ сбрасывать/не продлевать; простой сохраняется отрицательным evidence. M1-S1 OPEN, stability NOT PASS, M2-G0 BLOCKED. Heartbeat остаётся только read-only; одноразовый оператор18.09 НЕ повторять. Ниже исторические checkpoints.

**18 сентября, 04:05 МСК — бот остановлен, плановый backup требует оператора.** После ранее сохранённого отказа03:04 произошли public_readiness_failed03:25:13 (попытка3/10, cleanup=proven) и relay_exit25503:27:56 на startup попытки4/10; recovery_disposition=stop_non_retryable, control_closed. Плановый Scheduler backup стартовал03:30:01; новая generation `daily-20260918T033035-005adf9dd1ba492f83987e7cf36e2bee` проверена по authentication/binding/ciphertext/plaintext. Но restart03:31:11 отклонён с recovery_history_blocked/78; cleanup дополнительно зафиксировал stop_control_create_failed/70, а journal03:37:45 — failed_operator_required, admission_hold=true, cleanup_proven=true. Backup LastTaskResult=1, Main/Health отключены, процессов и listener нет, lease неактивна, local/public=false. Пауза не завершена; этот цикл НЕ засчитан, остаётся1 из минимум2 успешных плановых циклов. Четыре БД по отдельности PASS; количества87tasks/85receipts/16delivery rows сохранены, offset375633502/revision59615, очередь пуста. Полная runtime validation и freshness guard блокируются RuntimeAdmissionPaused; delivery/reconciliation свежим независимым срезом не подтверждены. Причина выхода relay и публичных отказов UNKNOWN; Python drift не установлен. Исходный FAIL04:03 сохранён в canonical `.runtime/m1-s1-observation-20260918-0403-failed.json`; scoped read-only диагностика `.runtime/m1-s1-paused-backup-diagnostic-20260918-0405.json`, SHA256 `4e0da5ae51e0fd1e4be8412e418fe4557da7d57c2f393585df812f93757ea8fd`; инцидент BACKUP_RESTART_BLOCKED_20260918T003111 в EVIDENCE. Наблюдатель production не менял, старые operators не повторял. Для восстановления нужны отдельное согласование плана и разрешение владельца; heartbeat не снимает hold, не сбрасывает history и не меняет Scheduler. Срок16.09 08:00→19.09 08:00МСК остаётся фиксированным, новые реальные отказы учитываются. M1-S1 OPEN, stability NOT PASS, M2-G0 BLOCKED; source/deployed0bd63db, merge/main26860ad, релизv1.0.2 и прежняя квалификация неизменны. Ниже исторические checkpoints.

**18 сентября, 03:19 МСК — новая остановка, полное восстановление пока не подтверждено.** В 03:04:31 authenticated history зафиксировала public_readiness_failed: local=true/public=false, supervisor exit1, попытка2/бюджет10, cleanup=proven; в03:05:31 штатно началась попытка3. В исходном срезе03:06:08 local/public=false, listener отсутствует, lease неактивна, Health result1; процессы нового запуска присутствуют. Четыре БД PASS, данные87/85/16 сохранены, offset375633502/revision59533, очередь пуста, unknown0, reconciliation=false. Один диагностический повтор03:19 подтвердил public HTTP200/906мс при deadline5000мс; local HTTP400 не является контрактной проверкой из-за пропущенного обязательного Host-заголовка в диагностике. Исходный FAIL сохранён, дальнейших повторов в этом запуске нет. Причина публичного отказа UNKNOWN; связь с Python drift не доказана. Плановая копия17.09 проверена, циклcomplete/result0, зачтена1 из2; следующая18.09 03:30. Production не менялся. Квитанции canonical `.runtime/m1-s1-observation-20260918-0306.json` (SHA256 `8fe42b344f2bfd4a0596c4f18648656d32c5fe6482bcf33cabc16251542f0a8a`) и `.runtime/m1-s1-readiness-followup-20260918-0319.json` (SHA256 `e18776a38b146ae0c2088627d4995c66b61652f93e14f93c5d77113a3e05fc78`), инцидент PUBLIC_READINESS_20260918T000431 в EVIDENCE. Сессия16.09 08:00→19.09 08:00МСК без переноса; M1-S1 OPEN, stability NOT PASS, M2-G0 BLOCKED. Source/deployed0bd63db, merge/main26860ad, v1.0.2 и квалификация неизменны. Следующий шаг — штатная read-only проверка восстановления и полного планового backup. Ниже исторические checkpoints.

## Проверка 17.09.2026, 22:37 МСК — остановка по публичной readiness и штатное восстановление

В 22:31:50 МСК authenticated history зафиксировала `public_readiness_failed` на стадии steady: local=true/public=false, supervisor exit=1, causal Core/relay exit codes отсутствуют, cleanup=proven. Это новая неплановая остановка, а не успешный непрерывный интервал. После подтверждённой очистки штатный recovery выдержал 60 секунд; в 22:32:50 началась попытка 2 при retry_budget=10. Наблюдатель restart/reset/restore не выполнял.

Срез 22:37:04: local/public=true, одна логическая цепочка supervisor/Core/relay, один listener8765 (PID11600) и одна active lease. Supervisor остался прежним, дочерние процессы заменены штатным recovery. Четыре БД PASS; 87 задач, 85 receipts и 16 подтверждённых частей сохранены; offset375633501/revision58475, очередь пуста, unknown=0, reconciliation=false. Плановая копия17.09 03:30 проверена, её полный цикл complete и Scheduler result0; зачтена 1 из минимум2, следующая18.09 03:30.

Квитанция: canonical `.runtime/m1-s1-observation-20260917-2237.json`, SHA256 `ea64d4b58af2920fa7e4b5bfe06f889b60bf21dca05110f8a41ae6773e5b9e26`; инцидент `PUBLIC_READINESS_20260917T193150` в EVIDENCE. Доказаны причина завершения supervisor и ограниченное восстановление; первопричина публичного отказа и точная длительность недоступности UNKNOWN. Текущая успешная проверка не объясняет прошлый отказ. Связь с инцидентом09:59 или Python drift не установлена; неизменные contracts/tests/reviews не повторялись. Подход systematic-debugging ограничил выводы подтверждённой границей отказа, без правок кода и предположений о сети.

Фиксированная сессия **16.09 08:00 → 19.09 08:00 МСК** продолжается без переноса, с учётом нового реального отказа при итоговой оценке. Source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`, merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, v1.0.2 и прежняя квалификация TXT неизменны. M1-S1 OPEN, устойчивость NOT PASS, M2-G0 BLOCKED. Следующий шаг — тот же read-only heartbeat и проверка следующего планового backup. Нижние checkpoints исторические; документация изменена локально без commit/push.

## Проверка 17.09.2026, 09:59–10:01 МСК — публичный отказ, повторный запрос успешен

Первичный срез 09:59:39: local=true, public=false. Исходный FAIL сохранён в canonical `.runtime/m1-s1-observation-20260917-0959.json`, SHA256 `f326b55f76aaa90cd5c0221a6318506abf28199d65c1f827bdb09c3f001aa7b1`. Процессы, authenticated history и fallback прежние; новая остановка не обнаружена. Четыре БД и backup PASS; 87 задач/85 receipts/16 частей сохранены, offset375633493, одна active lease, очередь пуста, unknown=0, reconciliation=false.

Один разрешённый read-only повтор публичного `/readyz` в 10:01:11 вернул HTTP200, точное ожидаемое тело, 797 мс при deadline5000 мс. Квитанция `.runtime/m1-s1-observation-20260917-1001-public.json`, SHA256 `74680748083bf376f52b7556bb14f18acec7a4a0184750209969e617bb91ad30`. Исходный boolean probe не сохранил HTTP/ошибку; первопричина UNKNOWN. Повторный успех не отменяет исходный отказ и не доказывает его связь с Python drift либо прежними инцидентами. Инцидент `PUBLIC_READINESS_20260917T065939` открыт для итоговой оценки; production не менялся, перезапусков со стороны наблюдателя нет.

Фиксированная сессия **16.09 08:00 → 19.09 08:00 МСК** продолжается без переноса; 1 из минимум 2 плановых копий, следующая18.09 03:30. Source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`, merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, v1.0.2 и принятые проверки/задача/TXT неизменны. M1-S1 OPEN, устойчивость NOT PASS, M2-G0 BLOCKED. Следующий шаг — тот же read-only heartbeat; новый реальный отказ учитывать в финальном verdict, не запускать новый Gate или окно.

## Уточнение владельца 17.09.2026, 08:20 МСК — фиксированная сессия 16.09 08:00 → 19.09 08:00

Перепроверено по EVIDENCE.python_pinning_20260916: закрепление Python и финальная проверка runtime завершены **16.09 07:55:05 МСК**, до указанного владельцем начала. Единственный действующий срок наблюдения: **16 сентября 08:00:00 → 19 сентября 08:00:00 МСК** (`2026-09-16T05:00:00Z` → `2026-09-19T05:00:00Z`). Не переносить его автоматически из-за пропусков проверок, лимитов Codex, сжатия контекста или старых записей о сбросе. В назначенный срок оценить фактические критерии; недостаток доказательств означает честный NOT PASS с причиной, а не вымышленный PASS или самовольное новое окно.

По прямому сообщению владельца пропуск 17.09 06:23–08:16 вызван исчерпанием недельного лимита Codex, а не отказом Nobus Space. Это источник OWNER_REPORTED; отдельная история лимитов не проверялась. Новых остановок runtime в свежем срезе 08:16 нет, процессы и authenticated history прежние. Остальные исторические причины пропусков этим объяснением не подменяются. Все пропуски внутри сессии засчитываются в календарную длительность по решению владельца, оставаясь непроверенными интервалами, а не выполненными PASS-проверками.

В текущую сессию возвращены **38 существующих подтверждённых срезов** после 16.09 08:00, без повторных запусков и без дублей; старые квитанции и история окон сохранены. Плановая копия 17.09 03:30 и полный цикл PASS засчитаны: **1 из минимум 2**, следующая 18.09 03:30. Последняя фактическая проверка 17.09 08:16: local/public и четыре БД PASS, данные 87/85/16 сохранены, offset375633492, одна active lease, очередь пуста, unknown=0, reconciliation=false, backup проверен. Прошло около 24 часов 16 минут календарного времени сессии на момент этого среза; полнота наблюдения ограничена сохранёнными пропусками.

Тот же heartbeat `m1-s1-mvp1` обновлён штатно, ACTIVE/30 минут, отчёт каждой проверки; production не менялся. Source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`, merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, v1.0.2 и прежние проверки/реальная задача/TXT неизменны. M1-S1 OPEN, устойчивость NOT PASS, M2-G0 BLOCKED. Все иные сроки ниже — история, а не действующее правило.

## Решение владельца 17.09.2026, 08:18 МСК — продолжать окно без сбросов из-за пропусков проверок

Владелец явно отменил правило перезапуска окна при разрыве проверок. Продолжается сессия **17.09 01:46:52 → не ранее 20.09 01:46:52 МСК**; плановая копия 17.09 03:30 сохраняет зачёт: 1 из минимум 2, следующая 18.09 03:30. Последний фактический срез 08:16 успешен: local/public, четыре БД, backup, одна цепочка Core/supervisor/relay и active lease; новых остановок нет, данные сохранены, очередь пуста, unknown=0. Накоплено около 6 часов 29 минут календарного времени сессии.

Пропуски проверок засчитываются в длительность по решению владельца, но не превращаются в выполненные проверки: интервал 06:23–08:16 сохранён как `NOT_OBSERVED_ACCEPTED_BY_OWNER`, причина пропуска UNKNOWN. Непрерывная доступность в нём не доказана. Фактические отказы по-прежнему сохраняются и сообщаются; итоговый verdict должен явно учитывать неполноту наблюдения. Старые квитанции, окна и первоначальное решение о сбросе сохранены как история; текущий отсчёт восстановлен в EVIDENCE вместе с девятью прежними срезами и новым срезом 08:16.

Существующий heartbeat `m1-s1-mvp1` обновлён: тот же id/задача, ACTIVE, каждые 30 минут, отчёт каждой проверки, без restart/restore/reset или production-мутаций. Source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`, merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, v1.0.2 и принятые проверки/реальная задача/TXT неизменны. M1-S1 OPEN, устойчивость NOT PASS, M2-G0 BLOCKED. Ниже — исторические правила и checkpoints.

## Точка продолжения 17.09.2026, 08:16 МСК — бот работает, новый разрыв наблюдения

Local/public PASS, четыре БД исправны, очередь пуста, неизвестных доставок нет, reconciliation=false. Сохранены 87 задач, 85 receipts и 16 подтверждённых частей; offset375633492 не уменьшился, revision55072, одна активная lease. Цепочка Core/supervisor/relay и listener прежние; authenticated history и fallback не изменились, новых остановок нет. Main Running, health Ready/0, backup Ready/0; копия `daily-20260917T033035-f108d31681af4818b0c7d32a5a0f1436` вновь проверена, цикл complete.

Между подтверждёнными срезами 06:23:22 и 08:16:08 прошло 1 час 52 минуты 45 секунд. Для heartbeat 06:55, 07:25 и 07:56 нет завершённых квитанций; scoped inventory не обнаружил промежуточных срезов. Причина пропуска UNKNOWN; это разрыв наблюдения, не доказанная остановка бота. По согласованному правилу новое окно **17.09 08:16:08 → не ранее 20.09 08:16:08 МСК**. Предыдущее окно с девятью срезами и одной успешной плановой копией сохранено целиком в EVIDENCE.observation.prior_windows. Эта копия остаётся валидным доказательством backup, но не засчитывается как созданная внутри нового окна: в нём пока 0 из минимум 2 плановых копий. Следующие плановые запуски — 18 и 19 сентября в 03:30 МСК.

Квитанция: canonical `.runtime/m1-s1-observation-20260917-0816.json`, SHA256 `6491487c987e502a96fa513da4573d539e308c2ffcb014771a0249309b2fe18d`. Production и расписание не менялись; source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`, merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, v1.0.2, закреплённый Python и исторические проверки/реальная задача/TXT сохранены. M1-S1 OPEN, устойчивость NOT PASS, M2-G0 BLOCKED. Продолжать тот же read-only heartbeat с итогом каждой проверки; нижние сроки исторические.

## Точка продолжения 17.09.2026, 03:54 МСК — первая плановая копия после закрепления Python успешна

Scheduler Backup: запуск 03:30:01, Ready/LastTaskResult=0; полный цикл завершён в 03:32:12 (131 секунда от запуска, в пределах бюджета). Новая generation `daily-20260917T033035-f108d31681af4818b0c7d32a5a0f1436` прошла authentication/binding/ciphertext/freshness и проверки содержимого. Manifest digest `sha256:e65ca4c0f2d688846274ddb53616fb6a2753749341edd0280abca3638d237589`. Это **первая из минимум двух плановых копий** текущего окна; следующий запуск 18.09 03:30 МСК.

Authenticated history: planned_stop/exit0/cleanup proven в 03:30:27, control_closed; control_ready и starting в 03:31:10. Новых неплановых завершений и fallback-событий нет. После планового перезапуска одна логическая цепочка Core/supervisor/relay, один listener и активная lease; local/public PASS, main Running, health Ready/0. Четыре БД исправны, 87 задач/85 receipts/16 подтверждённых частей сохранены, offset375633491 не уменьшился, revision54035, очередь пуста, unknown=0, reconciliation=false.

Квитанция: canonical `.runtime/m1-s1-observation-20260917-0354.json`, SHA256 `eb60a8b6ddde6ba152e82eabd6aa77b45220d9886a861aefb87183e2e3e85002`. Интервал проверок 31 минута 48 секунд; окно остаётся **17.09 01:46:52 → не ранее 20.09 01:46:52 МСК**, прошло 2 часа 7 минут. Наблюдатель production не менял; остановку и запуск выполнил штатный плановый backup. Source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`, merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, v1.0.2 и принятые проверки/реальная задача/TXT неизменны. M1-S1 OPEN, устойчивость NOT PASS, M2-G0 BLOCKED. Следующий шаг — продолжать тот же read-only heartbeat; сроки и состояния ниже исторические.

## Точка продолжения 17.09.2026, 01:46 МСК — бот доступен, разрыв наблюдения

Проверка local/public, четырёх БД и резервной копии успешна. Новых завершений и fallback-событий нет, цепочка процессов прежняя: один логический Core/supervisor/relay, listener и активная lease. Сохранены 87 задач, 85 receipts и 16 подтверждённых частей; очередь пуста, unknown=0, reconciliation=false. Offset 375633491, revision 53537. Health захвачен в состоянии Running с LastTaskResult=0 отдельными чтениями; завершение текущего запуска не предполагается, прямые local/public проверки успешны. Backup LastTaskResult=1 относится к прежнему отказу 16.09 03:30; последующий ручной цикл завершён, его копия проверена.

Между подтверждёнными срезами 00:42:10 и 01:46:52 прошло 64 минуты 41 секунда. Heartbeat 01:13 остановился на предварительном чтении, затем ответ о Telegram-уведомлениях проверял только расписание; промежуточного подтверждённого среза нет. Остановка бота не обнаружена. По согласованному критерию перезапущено только окно: **17.09 01:46:52 → не ранее 20.09 01:46:52 МСК**, минимум две успешные плановые копии. Ближайшая — 17.09 03:30 МСК. Предыдущее окно со всеми 21 срезами сохранено в EVIDENCE.observation.prior_windows. Новая квитанция: canonical `.runtime/m1-s1-observation-20260917-0146.json`, SHA256 `2939ccca4b5fb43f489976e75349ebd21889e0e509cb1b07d9b39a54b9ebd66e`.

Production не менялся. Source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`, merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, v1.0.2, закреплённый Python и принятые проверки/задача/TXT неизменны. Тот же heartbeat работает каждые 30 минут; отчёт о каждой проверке подготовлен для глобального notifier, фактическая доставка в Telegram не подтверждена. M1-S1 OPEN, устойчивость NOT PASS, M2-G0 BLOCKED. Сроки ниже исторические.

## Точка продолжения 16.09.2026, 13:24 МСК — бот доступен, окно наблюдения начато заново

Local/public, четыре БД и свежая резервная копия проверены; новых завершений и fallback-событий нет, процессы прежние. Сохранены 87 задач, 85 receipts и 16 подтверждённых частей; очередь пуста, неизвестных доставок нет, reconciliation=false. Offset вырос до 375633489. Первый срез показал неактивную polling lease; отдельное read-only чтение в 13:24:27 подтвердило одну активную lease и рост revision 50606 → 50609. Исходный результат сохранён: принятый код освобождает lease после каждого polling batch, но отсутствие подробностей первого среза не позволяет различить null и истечение срока. Остановка runtime не установлена.

Между подтверждёнными полными срезами 12:17:07 и 13:23:54 прошло 66 минут 47 секунд. Предыдущий heartbeat ограничился подготовительным чтением; ответ о настройке уведомлений не проверял runtime. По согласованному правилу новое окно **16.09 13:24:27 → не ранее 19.09 13:24:27 МСК**, минимум две успешные плановые копии; ближайшая 17.09 03:30 МСК. Предыдущее окно и все доказательства сохранены в EVIDENCE.observation. Квитанции: canonical `.runtime/m1-s1-observation-20260916-1323.json` и `.runtime/m1-s1-observation-20260916-1324-lease.json`.

Source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`, merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, v1.0.2, закреплённый Python и прежние проверки/реальная задача/TXT неизменны. Production не менялся. Тот же heartbeat продолжает проверку каждые 30 минут с отчётом после каждого запуска. M1-S1 OPEN, устойчивость NOT PASS, M2-G0 BLOCKED. Указанные ниже сроки окна исторические; checkpoint ремонта Python сохраняется.

## Точка продолжения 16.09.2026, 07:55 МСК — Python закреплён, наблюдение возобновлено

**Уточнение владельца 16.09: отчёт после каждой проверки.** Существующий heartbeat обновлён: каждый запуск, включая успешный, завершается кратким итогом с временем МСК, доступностью бота, новыми сбоями, состоянием данных/backup и ходом окна. Доставка — через действующий глобальный Telegram notifier, без второй отправки и без новой задачи боту. Прежнее правило «только существенные изменения» ниже историческое. Период 30 минут, границы read-only и текущее 72-часовое окно не изменены; первая доставка в новом режиме ещё ожидается.

**Исправление внедрено, бот работает; устойчивость ещё не подтверждена.** Каноническая `.venv` переведена с кэша Codex на отдельную точную копию Python 3.12.14 в canonical `.runtime/production-python/cpython-3.12.14-ed91bed4/base`. Проверены 12 182 файла / 443 809 639 байт, отсутствие ссылок на кэш, действительная подпись Python и все 80 неизменных пакетов. Inventory digest `ec7bd777c9d08b348e719e5ae4a677bc1372a2be238178f99b14c628333e4e58`. Исходный `pyvenv.cfg` и три прежних WIP-документа сохранены рядом в `rollback` и `docs-before`.

Source/deployed **`0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`**, LIVE clean; merge/main **`26860adfeae84fa075a8f3cb3260e9d4c6dd9257`**. Published v1.0.2 → `82003c03d8a36015703472b472640ab4021fb416` неизменен. Код, тесты продукта, document 11, Scheduler Actions/config, пакеты и БД не заменялись. Прежние 210 PASS, Scheduler fixture и L1/L2/L3 сохраняются на своей ревизии; повторного полного цикла не было. Дополнительно прошли 10 синтетических проверок локального оператора и 3 целевых теста нового окружения. JUnit `isolated/.runtime/m1-s1/pinned-python-20260916.xml`, SHA256 `67f938258c038445cdfc02314854a51060e654b67da01dd2529b413c3a05fb95`.

Перед переходом актуализированы данные, backup и inputs; после hold выполнены штатный STOP в 07:44:34, `control_closed` и cleanup proven, новая проверенная prechange-копия, правка только cfg, readback под `pythonw` владельца и принятый backup/start. Пауза менее 5 минут, в пределах 20. Activation binding **`sha256:0c2b23037184c41a2dac3d6b94df38e5fa6f5103e25303438be46e8fc4af2c5b`** совпала: содержимое интерпретатора не менялось. Rebind/reset или удаление истории не выполнялись. Auto-review сначала отклонил непроверенный локальный оператор; после 10 синтетических safety checks та же команда штатно разрешена. Отклонённая попытка не имела эффектов, обхода не было.

Backup cycle complete в 07:48:48: `daily-20260916T074703-f23cdfe94ea4483db59e5b23607966b8`, manifest `sha256:a4b737d8a05608e93177defa45b8082fde27ce2eceb3cfe3243317ed04548aa3`. Retention переместила две принадлежащие ей копии в обратимый карантин, без удаления. Первые дополнительные verifier receipts дали STOP, поскольку проверяющий искал prechange по прежнему пути. В v3 исправлено чтение exact generation в карантине с проверкой ownership/inventory/authentication и исходного manifest digest: PASS. Исходные STOP сохранены как VERIFIER_DEFECT, а не падение runtime.

Срез 07:55: local/public PASS; один логический supervisor/Core/relay, listener 25384, одна active lease. Фактические Python images находятся в закреплённой копии либо `.venv` redirector, Job membership проверена. Прежние строки семи таблиц задач/доставки и logical digest business-notes сохранены: 87 tasks / 85 receipts / 16 confirmed parts, offset 375633488 монотонен, queue пустая, unknown 0, reconciliation false, четыре БД PASS. Main Running, health Ready/0; backup enabled. Его LastTaskResult 1 относится к историческому плановому отказу 16.09 03:30, а не к успешному ручному циклу. Модель/ASR 0; принятая квалификация text/TXT не повторялась.

**Возобновлён существующий heartbeat `m1-s1-mvp1`: ACTIVE, каждые 30 минут, в этой же задаче.** Новый T0 **16.09.2026 07:55:05 МСК**, самый ранний итог **19.09.2026 07:55:05 МСК** (`04:55:05.197862Z`). Старое окно сохранено, не засчитывается. Нужны минимум две успешные плановые backup; ближайшие — 17 и 18 сентября в 03:30. Ручная копия не считается плановой. Разрыв более 60 минут перезапускает только окно; автоматические restart/restore/reset, изменения кода, новые model/ASR calls запрещены. Уведомления только о существенном изменении, отказе, действии владельца или завершении. Первый автоматический срез после возобновления ещё PENDING.

Исторический trigger остановок 10–14.09, конкретный процесс замены cached Python и причины кратких local/public readiness failures остаются UNKNOWN. Закрепление исключает зависимость production Python от обновляемого кэша, но не доказывает исправление кратких сбоев. При новом отказе сохранять первый FAIL и отдельно уточнять HTTP/error/deadline, не заменяя его последующим PASS.

Индекс — `EVIDENCE.python_pinning_20260916` и `observation`; итоговая квитанция canonical `.runtime/m1-s1-pin-python-final-v3-20260916.json`, SHA256 `d24a0612619df31af71504dc08c4828295364548c5d1f56864f09e991d4a1779`. Активные docs01/README/Gate index/Runbook/Workspace inventory/HANDOFF/EVIDENCE/CURRENT обновлены в изолированной копии; **документационная дельта локальная, не опубликована**. Исторические C6 receipts/sealed sources и document 11 не менялись, чужой WIP canonical сохранён. Nobus Memory Search снова MEMORY_OPERATION_FAILED; Health READY, scope только project:nobus-space. Обхода и записи в память нет.

Verdict: release v1.0.2 unchanged; maintenance accepted/merged; production RUNNING на закреплённом Python; реальная задача/TXT — прежний PASS; stability IN_PROGRESS/NOT PASS; M1-S1 OPEN; M2-G0 BLOCKED. Далее — согласованное наблюдение и плановые backup, не новая приёмка. Все шапки ниже исторические.

## Точка продолжения 16.09.2026, 07:24 МСК — runtime восстановлен, heartbeat остановлен владельцем

**Бот снова работает.** По прямому запросу владельца heartbeat `m1-s1-mvp1` переведён в PAUSED, прочитан обратно; автоматически возобновлять его нельзя. Выполнены одна точная смена activation binding и один recovery неудачного backup-цикла штатными командами принятого `0bd63db`. Код продукта, пакеты и БД не заменялись; модель/ASR и повторная квалификационная задача не запускались. Merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257` и v1.0.2 неизменны.

**Установленный механизм отказа после backup:** `.venv` ссылается на базовый Python в изменяемом кэше Codex. У базового `pythonw.exe` изменился SHA256 с `097e62213eeb18ec5badab18acaac76986e684695598b2aeb68334aafb6ba055` на `ed91bed4dc6c3329807b06895e7bd34667b27c55af228de006f44c65b5675bc0`. Версия осталась 3.12.14; Authenticode Valid, signer OpenAI OpCo, LLC. Все остальные группы activation inputs, код, assets, ASR inventory, Scheduler signatures, backup config и состав 80 пакетов совпали с принятым срезом. Только `installed_runtime` изменил binding. С новым binding воспроизведён `runtime_history_invalid`; старый binding принимал ту же неповреждённую историю. После exact rebind запуск прошёл. Конкретный процесс/событие замены бинарника UNKNOWN: дата создания файла 15.09 16:47:10 UTC не является журналом обновления. Причину более раннего публичного отказа этим фактом не подменять.

Перед восстановлением проверены свежая копия, четыре БД, отсутствие lease и штатный STOP; сохранены fingerprints всех прежних строк семи таблиц задач/доставки. Пять целевых синтетических тестов binding/rebind/staging/backup recovery прошли под Windows identity владельца с отдельным pytest mutex namespace. JUnit `.runtime/m1-s1/repair-env-20260916.xml`, SHA256 `fcb70c3bfa8ce0438a36d8287926cf2a3b4e2f1bf21de65e3614c80fe34b95c8`. Исторические 210 PASS и L1–L3 не повторялись и остаются привязанными к своему кандидату.

При отключённых main/health временно отключён только backup. Штатный rebind связал exact history head `sha256:f8631e827100955465050ac0b22af62f3de24bfbcddf40fe5d98e7d9d04a520d` с новой binding `sha256:0c2b23037184c41a2dac3d6b94df38e5fa6f5103e25303438be46e8fc4af2c5b`, сохранив историю; event digest `sha256:898f906b90a86c506eda1a8304f48a06a7dca874e37c0c900490686ecc299c23`. Затем backup включён и один recovery точного failed digest `sha256:d5d36a6a947af17b52b21cabdebcda48eb99c6f29443fd8177816bee3e0077c3` завершился PASS в 07:22:49. Новая проверенная generation `daily-20260916T072108-d72108a744214cacaabbd697d66ec8f1`; журнал complete. Штатный retention переместил одно принадлежащее ему старое поколение в обратимый карантин, не удалил его. Исходный failed journal сохранён существующим recovery-механизмом.

Все прежние строки семи таблиц сохранены: 87 tasks / 85 receipts / 16 confirmed parts; offset375633480 не уменьшился, одна active lease. Один логический supervisor/Core/relay, listener37580; проверенные процессы состоят в Job. Очередь пуста, delivery unknown=0, reconciliation=false, четыре БД PASS. В 07:23:54 один bounded probe дал local=false/public=true; исходная причина UNKNOWN. В 07:24:38 прямые probes с прежними deadlines дали local HTTP200 за282мс и public HTTP200 за750мс; штатные local/public probes также PASS, без рестарта. Health Enabled/Ready/0, main Enabled/Running. Backup Enabled/Ready; его LastTaskResult1 остаётся квитанцией неудачного планового запуска03:30 — ручной recovery не переписывает этот факт и не считается плановой копией окна.

Санитизированные квитанции: canonical/.runtime/m1-s1-repair-binding-probe-20260916.json; m1-s1-repair-20260916-prepare.json; -rebind.json; -cycle.json; -final.json. Полный индекс и раздельные verdicts — `EVIDENCE.operator_recovery_20260916`. Прежние одноразовые operator scripts и новые intent не запускать повторно вслепую.

**Оставшаяся граница:** production всё ещё зависит от изменяемого базового runtime Codex. Для исключения повторения нужен отдельный точный переход на закреплённый production-интерпретатор, без ослабления binding и без слепого обновления зависимостей. Эта миграция не выполнена. Публичные/локальный transient probe-инциденты не объяснены полностью; 72-часовая устойчивость не подтверждена. M1-S1 OPEN, наблюдение PAUSED_BY_OWNER_AFTER_OPERATOR_RECOVERY/NOT PASS, M2-G0 BLOCKED. Никаких постоянных проверок, нового Gate или MVP2 без нового решения владельца. Все шапки ниже исторические.

## Точка продолжения 16.09.2026, 03:55 МСК — бот остановлен после отказа планового backup-цикла

**Текущее состояние: runtime недоступен, автоматическое восстановление наблюдателем запрещено.** Штатный STOP для плановой копии подтверждён в 03:30:27: exit 0, `planned_stop`, `control_closed`, cleanup=proven. Новая generation `daily-20260916T033034-7681408143584acab0c580d81cf68e8a` создана в 03:30:35 и прошла authentication/binding/ciphertext/plaintext/freshness. Но повторный запуск main в 03:30:59 завершился `recovery_history_blocked`, exit 78 (fallback в 03:31:09). В 03:37:39 цикл записал `failed_operator_required`, admission_hold=true, cleanup_proven=true; backup LastTaskResult=1 теперь относится к НОВОЙ попытке 16.09, а не к истории до активации. Вторичный stop при cleanup дал `stop_control_create_failed`, exit 70 в 03:37:24; итоговая очистка подтверждена журналом цикла.

В 03:52–03:53: main/health Disabled, main LastTaskResult=78; backup Enabled/Ready/1. Scoped LIVE Python-процессов и listener8765 нет, lease неактивна, local/public=false. Четыре БД PASS; 87 tasks / 85 receipts / 16 confirmed parts сохранены, offset375633480, revision49185; очередь пуста, pending/leased/unknown/failed delivery=0, reconciliation=false. Отдельный SSH PID в этом диагностическом срезе не перечислялся; нельзя подменять это отсутствием relay, хотя cleanup цикла подтверждён.

Обычный read-only observer корректно вернул `RuntimeAdmissionPaused`; его байты не менялись. Дополнительная read-only диагностика сохранила защищённую паузу и отдельно проверила копию/данные. Гипотеза о повреждённой истории не подтверждена: в 03:55 та же аутентифицированная история с сохранённым binding `sha256:f04221363e01bdb81a77eecfb1142a839aa1e84c23bbd5d0493858f6c84be5a1` дала recovery state=new, next_attempt=1, latch отсутствует. Это НЕ свежая проверка действующей activation binding. Точный компонент, из-за которого реальный запуск получил exit78, пока UNKNOWN; нельзя слепо повторять rebind/recovery или объявлять установленный дефект кода.

Инцидент `BACKUP_RESTART_BLOCKED_20260916T003109`, квитанция canonical/.runtime/m1-s1-observation-20260916-0350.json. Failed-cycle digest `sha256:d5d36a6a947af17b52b21cabdebcda48eb99c6f29443fd8177816bee3e0077c3` — только сохранённый факт для последующего сверенного операторского плана, не разрешение на recovery. Плановая generation не засчитывается в критерий: копия исправна, но полный цикл с восстановлением runtime провален. Окно устойчивости заблокировано; прежний срок 19.09 03:17 больше не действует. После восстановления потребуется новое непрерывное окно с двумя успешными полными плановыми backup-циклами. История всех срезов сохранена.

Следующий шаг вне автоматического восстановления: сверить фактические launch inputs с сохранённой binding и подготовить точный минимальный операторский план восстановления. Heartbeat продолжает только read-only наблюдение, не снимает hold, не меняет Scheduler/code/config, не делает reset/rebind/restart/restore. Source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c` установлен; merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, release v1.0.2 и исторические PASS кандидата/задачи/TXT сохранены, но не доказывают текущую работоспособность. M1-S1 OPEN, наблюдение BLOCKED_RUNTIME_STOPPED_BACKUP_CYCLE_FAILED/NOT PASS, M2-G0 BLOCKED. Старые шапки ниже исторические.

## Точка продолжения 16.09.2026, 03:17 МСК — публичный отказ, штатное восстановление и новое окно

Аутентифицированная история фиксирует завершение попытки 1 в 03:02:30 МСК: `public_readiness_failed`, стадия `steady`, exit 1, local=true/public=false, Core/relay exit codes отсутствуют, cleanup=proven. После штатного ожидания 60 секунд в 03:03:30 запущена попытка 2 из бюджета 10. Это восстановление самого принятого runtime, не действие наблюдателя. Причина остановки на границе supervisor установлена; первопричина публичного отказа UNKNOWN: HTTP-статус и тип сетевой ошибки не сохранены. Связь с инцидентом 15.09 19:51 не доказана. Новый инцидент `PUBLIC_READINESS_20260916T000230` открыт; стабильность не подтверждена.

Срез 03:17:27: local/public true/true, четыре БД и backup PASS; одна логическая цепочка Core/supervisor/relay, один listener и active lease. Core/relay заменены штатным восстановлением, supervisor прежний. Данные 87 tasks / 85 receipts / 16 confirmed parts сохранены; offset 375633480, revision 49132; очередь пуста, unknown=0, reconciliation=false. Main Running, Health Ready/0. Backup LastTaskResult=1 относится к прежней попытке до активации; следующая плановая копия 16.09 03:30, текущая ручная копия проверена и в счёт плановых не входит.

Между последними подтверждёнными срезами 02:12:56 и 03:17:27 прошло 64 минуты 31.155575 секунды. У предыдущего heartbeat нет завершённой квитанции; чтение статуса для ответа владельцу не являлось runtime-срезом. Причина отсутствия среза UNKNOWN. По правилу gap >60 минут начато пятое окно: **16.09.2026 03:17:27 → не ранее 19.09.2026 03:17:27 МСК**, плюс минимум две плановые проверенные копии и закрытие эксплуатационных инцидентов. Четыре предыдущих окна и все разрывы сохранены. Квитанция: canonical/.runtime/m1-s1-observation-20260916-0317.json.

Source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`, merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, опубликованный v1.0.2, принятые тесты/reviews и реальная задача/TXT остаются неизменными. Изменены только локальные документы и санитизированное evidence, без публикации. M1-S1 OPEN; наблюдение IN_PROGRESS_WITH_OPEN_INCIDENT/NOT PASS; M2-G0 BLOCKED. Следующий шаг — прежний read-only heartbeat с проверкой планового backup и повторяемости публичного отказа; без restart/restore/reset, изменения кода или новых квалификаций. Старые шапки и сроки ниже исторические.

## Точка продолжения 16.09.2026, 01:08 МСК — третий разрыв наблюдения, runtime без новых завершений

Срез01:08:30 МСК: local/public true/true,4БД и backup PASS, прежние процессы и одна active lease, history/fallback без новых завершений. Counts87 tasks/85 receipts/16 parts неизменны; offset375633480 монотонен, revision48628; очередь пуста, unknown0, reconciliation=false. Health Ready/0; backup LastTaskResult1 — прежняя доактивационная попытка15.09 03:30, следующая плановая копия16.09 03:30. Production не менялся.

После среза15.09 22:35:30 до16.09 01:08:30 прошло2ч33мин00.143394сек без подтверждённых промежуточных срезов. Причина пропуска UNKNOWN; текущий срез не доказывает доступность всего промежутка. Перезапущено только окно: **16.09.2026 01:08:30 → не ранее19.09.2026 01:08:30 МСК**, плюс минимум две плановые проверенные backup. Три прежних окна и разрывы сохранены в EVIDENCE.observation; текущая квитанция canonical/.runtime/m1-s1-observation-20260916-0108.json.

Инцидент public=false15.09 19:51 не повторился, но исходная причина UNKNOWN и acceptance остаётся открытым. Наблюдение IN_PROGRESS_WITH_OPEN_INCIDENT/NOT PASS, M1-S1 OPEN, M2-G0 BLOCKED. Ремонт/source/merge/release и реальная задача/TXT не обнуляются. Продолжать только прежнее read-only наблюдение; повторяющиеся разрывы относятся к полноте наблюдения, не к установленным остановкам бота. Старые сроки ниже исторические.

## Точка продолжения 15.09.2026, 21:30 МСК — второй разрыв наблюдения, runtime работает

Срез21:30:38 МСК: local/public true/true,4БД и backup PASS, прежние Core/supervisor/relay/listener и одна active lease, authenticated history/fallback без новых завершений. 87 tasks/85 receipts/16 parts сохранены; offset375633479 вырос на1, revision47767; очередь пуста, unknown0, reconciliation=false. Health Ready/0. Старый backup LastTaskResult1 по-прежнему относится к03:30 до активации, плановых копий в новом окне0.

Heartbeat20:57 завершился ответом инструмента `aborted` на read-only подготовке; срез runtime не получен, причина прерывания UNKNOWN. От последнего подтверждения20:25:13 до21:30:38 прошло65мин24.593527сек (>60мин). Перезапущено только окно: **15.09.2026 21:30:38 → не ранее18.09.2026 21:30:38 МСК**, с минимум двумя плановыми проверенными backup. Предыдущее окно,19срезов и открытый public-инцидент сохранены в EVIDENCE.observation.prior_windows/incidents; разрыв — в gaps. Квитанция canonical/.runtime/m1-s1-observation-20260915-2130.json.

Инцидент public=false19:51 не повторился в текущем срезе, его первичная причина остаётся UNKNOWN и acceptance открыт. Перезапуск окна не закрывает этот инцидент и не обнуляет принятый ремонт/реальную задачу/TXT. Production не менялся. Наблюдение IN_PROGRESS_WITH_OPEN_INCIDENT/NOT PASS, M1-S1 OPEN, M2-G0 BLOCKED. Следующий шаг — прежний read-only heartbeat; старые даты окончания ниже исторические.

## Точка продолжения 15.09.2026, 19:52 МСК — кратковременный отказ публичной проверки, причина UNKNOWN

Срез 19:51:04 МСК: local=true, public=false. Четыре БД и backup PASS; прежние процессы, listener и одна active lease, authenticated history и fallback без новых завершений. Данные 87 tasks/85 receipts/16 parts, offset375633478 сохранены; checkpoint revision47374. Health Ready/0. Новый отказ относится к публичной проверке, а не к доказанной остановке Core/relay.

Гипотеза для минимальной диагностики: кратковременный отказ публичного пути при исправном локальном Core. Единственная уточняющая пара GET /readyz с прежними deadlines, без proxy/redirect: 19:52 local HTTP200/body match за297мс; public HTTP200/body match за1203мс. Никаких production-мутаций, restart/restore/reset или сообщений модели не выполнялось. Причина первого public=false **UNKNOWN**: исходный boolean probe не сохраняет HTTP status/exception, поэтому нельзя утверждать timeout, DNS, TLS или502. Успешный повтор не отменяет первоначальное свидетельство.

Санитизированная квитанция canonical/.runtime/m1-s1-observation-20260915-1951.json связывает исходный срез, уточняющий read-only результат и incident PUBLIC_READINESS_20260915T165104. Наблюдение **IN_PROGRESS_WITH_OPEN_INCIDENT**, устойчивость NOT PASS. Интервал между полными срезами31мин41сек, разрыва>60минут нет; окно пока не перезапускалось. Срок18.09 10:49:52 МСК — лишь нижняя временная граница, не обещание PASS при открытом инциденте. Следующий heartbeat должен сопоставить публичную доступность, health и authenticated exits/recovery; не повторять приёмку или менять код автоматически. Все принятые source/merge/release и квалификация TXT сохраняются, M1-S1 OPEN, M2-G0 BLOCKED.

## Точка продолжения 15.09.2026, 10:49 МСК — новое окно наблюдения после пропуска среза

Проверка 10:49:52 МСК: local/public readiness и целостность четырёх БД PASS; прежняя одна логическая Core/supervisor chain, relay, listener и active lease. Новых событий завершения нет, очередь пуста, unknown=0, reconciliation=false; 87 tasks/85 receipts/16 confirmed parts сохранены, offset375633478 не уменьшился, checkpoint revision45236. Backup проверена, cycle complete, новых плановых копий пока0. Health в момент среза Running/267009 — выполняющаяся проверка, не подтверждённый отказ. Production не изменялся.

Последний подтверждённый срез был 09:43:10 МСК; до нового прошло 66 минут 42.675982 секунды. У запуска heartbeat около10:15 нет завершённой квитанции; причина отсутствия среза UNKNOWN, остановка бота не установлена. По согласованному правилу gap>60минут прежнее окно не засчитывается. Его два среза и итог сохранены в EVIDENCE.observation.prior_windows, разрыв — в gaps. Новый старт **15.09.2026 10:49:52 МСК**, самый ранний итог **18.09.2026 10:49:52 МСК**, при непрерывном наблюдении и минимум двух плановых проверенных backup. Квитанция: m1-s1-observation-20260915-1049.json. Это перезапуск только окна наблюдения, не runtime, тестов, квалификации или Gate.

Source/deployed0bd63db, merge26860ad, releasev1.0.2, квалификация результата/TXT и независимые проверки остаются действительными. Heartbeat m1-s1-mvp1 продолжает прежний read-only режим; production restart/restore/reset не выполнялись. M1-S1 OPEN, стабильность IN_PROGRESS/NOT PASS, M2-G0 BLOCKED. Ниже прежние сроки окна являются историческими; актуальные время и samples находятся в EVIDENCE.observation.

## Точка продолжения 15.09.2026, 08:55 МСК — квалификация PASS, наблюдение начато

**Обновление 15.09, 09:43 МСК:** первый автоматический heartbeat фактически выполнен и проверен. Local/public readiness, четыре БД, очередь, доставка и backup проходят проверки; процессы и authenticated history не изменились, новых остановок нет. 87 tasks/85 receipts/16 parts; offset 375633478, revision44974, одна active lease. Между срезами 47 мин 54 с — окно не перезапускается. Planned backup count пока0; срок самого раннего итога прежний, 18.09 в08:55 МСК. Первоначальный статус ожидания первого запуска ниже исторический; актуальные samples находятся в EVIDENCE.observation. Это подтверждение работы автоматики, не PASS устойчивости за72часа.

Принятый source/deployed `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c` продолжает работать; merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`, одинаковый tree `fd9b3f5e78fecf453e6ad28bf663d4a1797486c3`. Published release остаётся v1.0.2 без перемещения. Freeze, 210 PASS, финальный Scheduler fixture и L1/L2/L3 PASS действительны; новых product-code/dependency/config изменений и deploy не было. Зона checkpoint прежняя: три документа в изолированной копии, санитизированные локальные квитанции и разрешённый heartbeat, без публикации этого WIP.

Владелец явно разрешил заменяющую подачу вместо истёкшего уточнения. Перед отправкой 08:28 проверено: прежние task-runtime/business-notes logical digests ещё совпадали с prechange, новых исполнений не было. В 08:30 штатно отправлено одно заменяющее сообщение в тот же owner Telegram-контур. Задача `afb82083-3533-4cba-ae76-eb54b1153360` — **answered**, result revision 1, **worker attempts 1 / ASR 0**, один outbox message **acked / attempt 1**. В интерфейсе получены корректные три предложения и `nobus-result.txt`, 269 bytes. Две части text/document имеют одинаковый digest `sha256:c6e2a2f0723db840fc7ceda65e79fdfdd832fbcf2988335aa70f35befde85c47`, совпадающий с decoded sealed answer Core; обе имеют ACK с первой попытки. Дубликатов задачи или доставки не обнаружено. Дополнительное открытие TXT в Блокноте остановилось на `Computer Use app approval timed out`; обход и повтор не выполнялись. Проверка TXT основана на фактически полученном Telegram document, immutable content digest и валидированных ACK, а не на неподтверждённом чтении Блокнота.

Сохранность проверена полными row fingerprints до/после: все прежние строки task-runtime и business-notes сохранены без изменений. Добавлены ровно 1 task/ingress, 2 audit events, 1 sealed answer, 1 outbox message/receipt, 2 delivery parts. Итог 87 tasks, 85 receipts, 16 подтверждённых частей; offset 375633477 монотонен. Queue пустая, delivery_unknown=0, reconciliation=false, четыре БД healthy. Предыдущий diagnostic STOP в `qualification-result-20260915.json` классифицирован VERIFIER_DEFECT: сравнивался весь sealed JSON envelope вместо поля answer; исправленный v2 PASS, source не менялся. TypeError сериализации BLOB в первом read-only проверяющем исправлен без production effects.

Квитанции в canonical `.runtime/production-c6/m1-s1-transition-0bd63db/`: `qualification-before-20260915.json` SHA256 `dd994505fc63cb0d04dff13dea9638bdb6dec4d9cb0fa3bc6740a3e0c32fe92d`; `qualification-after-20260915.json` SHA256 `6d7d23f2c1371d61bdb139908f7a3b2a84259c176eaea483c38c3838e7d3caf0`; `qualification-result-v2-20260915.json` SHA256 `d0bb690b454cefe0bd1ae8608d85e0e87c9b815398704b9681e25dd2b418f587`. Ответы/тексты задач в durable evidence не сохранялись.

**Наблюдение IN_PROGRESS:** T0 `2026-09-15T05:55:15.895898Z` (08:55:15 МСК); самый ранний T72 `2026-09-18T05:55:15.895898Z` (08:55:15 МСК). Один heartbeat этой задачи `m1-s1-mvp1`, ACTIVE, каждые 30 минут, создан штатным automation_update; view подтвердил карточку. Нужны минимум две плановые backup внутри непрерывного окна. Разрыв проверенных срезов >60 минут начинает окно заново с сохранением истории. При неизменном нормальном состоянии уведомлений нет; только существенное изменение/отказ/действие владельца/итог. Heartbeat не делает restore/reset/restart, не меняет Scheduler, code/config и не вызывает модель/ASR или новые задачи.

Стартовый срез: local/public true/true, прежняя одна supervisor/Core chain и relay, listener PID16432, одна active polling lease, recovery history без новых завершений после startup03:16Z. Старые fallback exit78 (14.09 19:48Z) и exit70 `stop_control_create_failed` (19:54Z) относятся к первому переходу до успешного rebind/activation; они не новые остановки окна. Backup generation `daily-20260915T061518-636320af63f84a7ab878e8a61e62a7d4`, auth/binding/ciphertext PASS, cycle complete. Её ручной старт не считается плановой копией наблюдения; planned count=0. Ближайшая плановая backup 16.09 в03:30 МСК. Старый Scheduler LastTaskResult1 от15.09 03:30 остаётся объяснённой историей до успешного контролируемого цикла.

Read-only observer canonical `.runtime/m1-s1-observe-readonly.py`, SHA256 `c6508cbbbfc466cac523661733ca4827e8588688789ff457e81e466d8b4d7e06`, проверен вручную до расписания. Он использует принятые read-only validators и выдаёт только ограниченный санитизированный срез, не пишет production. В его WIP исправлены сохранение newline для bounded fallback parser и null NextRunTime у logon task; это ошибки проверяющего, не отказы runtime. Начальное evidence `m1-s1-observation-initial-20260915.json` во внешнем каталоге Codex visualizations, SHA256 `aaee2196f8b2817484c27b2cae876052df87bece994d5965443b37da838dfb5c`. Первый автоматический запуск ещё ожидается; его успех не заявлен заранее.

Следующий шаг — heartbeat по расписанию: сверить доступность, typed exits/recovery, one Core/lease, queue/unknown/reconciliation, integrity, offset и плановые backup. Не повторять квалификацию, freeze/review/suite/fixture или переход. Nobus Memory Search M1-S1 вновь MEMORY_OPERATION_FAILED, единственный Health READY только project:nobus-space; это не недоступность Obsidian и не основание для bypass. Недоступная глава Vibecoding не заменена выдуманным содержимым; Git/контракты/evidence сохранены.

Раздельный verdict: published release — v1.0.2 unchanged; maintenance candidate — accepted/merged, прежние L1/L2/L3 PASS; production — RUNNING/readiness PASS; real task/TXT — PASS; 72-hour stability — IN_PROGRESS, NOT PASS; M1-S1 OPEN, M2-G0 BLOCKED. Действующие разрешения сохранены, новых разрешений для согласованного наблюдения не требуется.

## Историческая точка 15.09.2026, 06:38 МСК

Maintenance принят и активирован, но квалификация результата/TXT и 72-часовая устойчивость ещё не подтверждены. [PR #32](https://github.com/streetenergy63reshik-del/nobus-space/pull/32) слит штатным merge: source `0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`, merge/main `26860adfeae84fa075a8f3cb3260e9d4c6dd9257`. Оба имеют tree `fd9b3f5e78fecf453e6ad28bf663d4a1797486c3`, diff пуст. LIVE clean на exact source `0bd63db…`, а не на новом непроверенном коде. Published release остаётся v1.0.2 → `82003c03d8a36015703472b472640ab4021fb416`; тег не перемещён, новый patch release не создан.

Freeze `m1-s1-source-freeze-0bd63db.json` (`43ca0132…`), review `m1-s1-review-evidence-0bd63db.json` (`f128ffc6…`), 210 PASS JUnit, финальный Scheduler fixture `613682de7d1243ffb3ee3ed9c08f11fd`, L1/L2/L3 PASS, D01 и security classification сохраняются. Код, тесты и runtime input document 11 после freeze не менялись. Старые freeze/fixture/review/merge pending ниже — история, не текущие блокеры. Зона этого checkpoint — только три документа HANDOFF/EVIDENCE/CURRENT в изолированной копии и локальные санитизированные квитанции. Предыдущие незакоммиченные версии сохранены в приватном transition-каталоге как `wip-*`; чужой WIP канонической копии не изменён. Эти новые документы не входят в принятый PR head и пока не опубликованы.

Переход: исходные XML всех трёх заданий, launcher/config и `prepare.json` сохранены и прочитаны обратно; prechange generation `prechange-20260914T223831-896207c0a4b84e6fa0ca7419a169c6a7` проверена до hold. Legacy STOP вернул 1 без причины; повторный read-only срез доказал отсутствие runtime и неизменные данные, исход отмечен `UNKNOWN_ALREADY_DOWN`, а не успешным STOP. Staging сначала остановился до mutation из-за отсутствующего exact rollback-подкаталога; после сверки старых bytes и создания этого каталога штатные installers успешно установили только три disabled задания. Новый config связан с фактическими LIVE bytes: `sha256:9c92ef673c03d77a97fefa1bd023091d37ac03f908739833b614208ca8caa645`.

Первый backup/start 14.09 завершился безопасным `recovery_history_blocked`/exit 78 и `failed_operator_required`; hold сохранён, cleanup доказан. 20-минутное окно не продлевалось бесконечными попытками. В 06:09 все три задания были отключены для диагностики. **Доказанная причина этого нового отказа:** bootstrap выполнен через `python.exe`, тогда как Scheduler запускает `pythonw.exe`; activation manifest включает `sys._base_executable`, и только компонент installed_runtime различался. Квитанции `identity-console-binding.json` и `identity-windowed-binding.json` подтверждают mismatch. Это не доказательство причины исторических остановок 10–13 сентября: их trigger остаётся UNKNOWN.

В 06:13 выполнен существующий точный rebind через `pythonw.exe` от прежнего authenticated digest; история не сброшена. Binding `sha256:f04221363e01bdb81a77eecfb1142a839aa1e84c23bbd5d0493858f6c84be5a1`, rebind receipt digest `sha256:dcede3abf4e4cb1a8e72e3b69ac52c16f4f437f2ea907325707fd208fab83b59`. Затем штатный backup cycle с подтверждением exact failed journal digest `sha256:ecec15ac982d94ee146eaa976a2758b901d94d11a217bb9e72c63d74557aa700` завершился `complete` в **06:16:37 МСК**: generation `daily-20260915T061518-636320af63f84a7ab878e8a61e62a7d4`; manifest `sha256:b8dcd6304ef11714f0bbf6469d5624201a66c5191cbfd33d4e4ee8ae7a79a91a`. Выполнены проверка generation/binding/STOP, restart_permitted, permit_admission, Enable/Start main, local/public readiness и Enable health. DB restore/reset не выполнялись. Штатная retention первого цикла переместила старую daily и prechange в recoverable quarantine, не удалила их; исходные backups не перезаписаны.

Свежий срез 06:33–06:38: main enabled/Running; health enabled/Ready/0; backup enabled/Ready/1, где 1 относится к неудачной плановой попытке 03:30 **до** успешного контролируемого recovery cycle. Следующая плановая backup — 16.09, 03:30 МСК. Local/public readiness true/true, stock integrity четырёх БД PASS, admission hold отсутствует. Одна supervisor chain `30220 → 12804`, одна Core chain `20196 → 33944 → 16432`, listener 8765 принадлежит `16432`; relay `37480 → 30480`. Два venv-host не являются вторым логическим Core. IsProcessInJob для Core, helpers и relay true; конкретный handle/id Job read-only API не раскрывает. Polling lease одна, active; offset `375633475`, revision `44221` на 06:33; offset не откатывался.

Сохранность на 06:33: task-runtime и business-notes имеют **те же полные logical digests**, что prechange; прежние telegram rows совпали (исключена только новая clarification, baseline таких rows не имел). По-прежнему 86 accepted tasks, 84 ACK receipts, 14 delivery parts; очередь пуста, delivery_unknown=0, reconciliation=false. Это фактический срез, не ограничение будущего числа задач.

Единственная квалификационная text-подача в 06:19 получила CLARIFY в 06:20, не результат. Accepted task/model execution не возникли; ASR 0. Владелец разрешил продолжение этой же подачи через Reply с дополнительным смысловым разбором и максимум одним выполнением. Однако clarification истекла **15.09 в 06:30:18.189092 МСК**, что подтверждено read-only `expires_at`; код штатно отклоняет просроченный Reply. Дополнительное сообщение не отправлено; собственный черновик очищен без отправки. Нельзя считать это результатом/TXT или повторять неизвестный effect: эффект проверен, исполнения нет. Для завершения квалификации нужна разрешённая новая подача вместо истёкшей, с тем же общим лимитом worker model 1 / ASR 0; это отличается от уже разрешённого продолжения через Reply.

Оставшиеся шаги конечны: разрешить заменяющую квалификационную подачу → получить корректный результат и TXT без дублей → сверить все accepted additions и прежние rows → начать один heartbeat этой задачи на 72 часа/30 минут, минимум две плановые backup, gap >60 минут начинает окно заново. Heartbeat не выполняет restore/reset/restart или изменения кода. До успешной реальной задачи heartbeat и окно **NOT STARTED**; старый smoke и текущие ~20 минут работы не выдаются за устойчивость. Автоматический отказ merge из предыдущего checkpoint снят точным разрешением и успешным merge; другие действительные разрешения не обнулены.

Evidence: canonical `.runtime/production-c6/m1-s1-transition-0bd63db/activation-readback-20260915-0638.json`, SHA-256 `aa3e86efb5f3f1feade1b6d9ba7348327327827c1023cd330f393fa842495183`; внешний `m1-s1-activation-checkpoint-20260915.json` связывает transition receipts и уточнённую topology. Поле processes первого readback имело слишком широкий диагностический фильтр: его не использовать как число Core; последующий exact Python-name/script/parent readback в 06:37–06:38 исключил diagnostic PowerShell/health и указан выше. Никакие argv/env/payload/task text в durable evidence не добавлены.

Nobus Memory: только project:nobus-space. Чтение главы Vibecoding «Тесты и приёмка» не состоялось: Search вернул MEMORY_OPERATION_FAILED; единственный Health после ошибки READY, другая релевантная формулировка Search дала тот же отказ. Это не «Obsidian закрыт». Недопустимый fallback и повторный неизменный поиск не выполнялись; Git/Runbook/evidence остаются основанием работы.

Раздельный verdict: published release — v1.0.2 unchanged; repaired candidate — frozen/L1/L2/L3 PASS, merged; deployed runtime — exact 0bd63db RUNNING, техническая readiness PASS, пользовательский результат ещё не квалифицирован; real task/TXT — CLARIFICATION_EXPIRED, NOT PASS; стабильность — NOT STARTED; M1-S1 — OPEN; M2-G0 — BLOCKED.

## Историческая точка 14.09.2026, 22:08 МСК

Проверенный source **`0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c`**, tree `fd9b3f5e78fecf453e6ad28bf663d4a1797486c3`, опубликован в `codex/m1-s1-stability`. [PR #32](https://github.com/streetenergy63reshik-del/nobus-space/pull/32) открыт, exact head совпал, GitHub `mergeable=true/clean`; main остаётся `88e58c8866db2384423f2b154df901a2e4af6c48`. Merge не выполнен.

Freeze `m1-s1-source-freeze-0bd63db.json`, SHA-256 `43ca0132251542f0f3dd3de7d4cd55d46b145decb5066d5f4a9779d01b18adcd`; review `m1-s1-review-evidence-0bd63db.json`, SHA-256 `f128ffc6014ac4ecd5c38acf0b8659dfca3bdb2c09eb80126abd583f3efc730c`. Все прежние L1/L2/L3 — PASS, обязательных findings нет. Сохранены 210 PASS JUnit `f71ff33c…`, D01 и security classification. Финальный реальный fixture `613682de7d1243ffb3ee3ed9c08f11fd`: transient 2, exhausted 3, permanent 1 attempt; LastTaskResult 0/23/29, cleanup proven; result SHA-256 `92c5df173abd2d52a510f8db7750047dcf958c01e8a01363c65ff5fb6607ad19`. Проверки не повторяются из-за публикации или этого документационного checkpoint.

Точный текущий блокер — автоматический контроль разрешений отклонил `github_merge_pull_request` для PR #32 с expected head `0bd63db…`, методом merge: он требует отдельного текущего подтверждения merge в защищённую main, несмотря на сохранённое общее разрешение владельца. Отказ произошёл до действия; повторный readback подтвердил open/unmerged. Обход другим каналом не выполнялся. Чтение branch-protection через интеграцию отдельно вернуло 403 `Resource not accessible by integration`; это не утверждение об отсутствии защиты. Первоначальный отказ push снят после проверки точного канонического public destination и прав push; push успешно выполнен.

Production не менялся. Exact исходные XML трёх заданий, health launcher и backup config сохранены с CreateNew/Flush/readback в canonical `.runtime/production-c6/m1-s1-transition-0bd63db/prepare.json`; это подготовка, не deploy. Следующий шаг: разрешённое слияние точного PR → свежая дельта LIVE inputs/backup/baseline → переход по плану ниже → реальная задача/TXT и сохранность → согласованный heartbeat 72 часа. До слияния production закрыт.

Раздельный verdict: published release — v1.0.2 unchanged; repaired candidate — frozen/L1/L2/L3 PASS, branch published, merge blocked by environment; deployed runtime — не изменён, последний проверенный срез DOWN; наблюдение — NOT STARTED; M2-G0 — BLOCKED. Этот checkpoint меняет только HANDOFF/EVIDENCE/CURRENT; frozen source и PR head не переопределяет.

## Предыдущий pre-freeze checkpoint

**Checkpoint 14.09.2026, 21:46 МСК:** published release остаётся v1.0.2; production не изменялся. Шестой frozen candidate `4777a2e59d07c18c2a99f1f3ddf818b81061c60b` отклонён после сбора всех L1/L2/L3 findings. Проверенный единый ремонт — `fcf99fc0f3a93881bc681e69f1f6f56f3676e246`, 210 PASS. Итоговый commit/tree после этой документационной правки связывается одной внешней freeze-квитанцией; до неё пакет DRAFT.

## Конечный результат и границы

M1-S1 завершается безопасным различением новых завершений, ограниченным восстановлением transient-отказов и понятным STOP при permanent/UNKNOWN/exhaustion; одним Core/Job/lease без повторения неизвестных effects и потери accepted tasks; совместимостью с backup; проверенным переходом, реальной задачей и TXT и началом согласованного наблюдения. Старый первичный trigger может остаться UNKNOWN. Отсутствующие исторические журналы не являются основанием для бесконечного поиска. Необязательные усиления не расширяют ремонт.

Зона владельца пакета: supervisor, два installer, Scheduler fixture, относящиеся tests, Runbook/CURRENT и этот Gate-пакет. Подготовленный docs01 сохранён; документ 11, C6 receipts, sealed sources, старые backups и recovery refs не менялись.

## Сохранённые доказательства

Внешние freeze/JUnit-квитанции находятся в указанном владельцем каталоге Codex visualizations / 2026 / 09 / 13 / 01a09c25-1d78-73e2-8691-be3db59a9fd1. Результаты Scheduler fixture сохраняются в изолированном worktree, `.runtime/m1-s1/scheduler-fixture/<run_id>/result.json`.

- Пятый кандидат: tree `cea7a00248d8c8bbd564d153436f967ab75f924c`; freeze SHA-256 `ba464970889610e1e264c3e05fd34aecbdbc3efc215425e73d620e3cf59505d4`.
- Существующие 218 PASS: `m1-s1-wip-dependent-host-20260914-1844.xml`, SHA-256 `3d9083ae2049d4e1e2123f495af6ee9dfb426f00c1bcc1a1ff6a4e8c52b4b200`; code/test/input blobs сверены с пятым freeze в `m1-s1-junit-binding-5b74368.json`, SHA-256 `6d0e39a4bdbcc00683c88c2411fdd20177966e36f2c0d3120d57b0e454066133`. Смена WIP → frozen сама по себе их не обнуляла. Для изменённого кода ниже получено новое evidence; неизменные Core/contracts не переоткрываются.
- Попытка `4f4d9f130bbc4f21a800d754e5e0fd1b`: exact tasks/process/result отсутствовали при повторной сверке; исход не объявлен успешным. Квитанция reconciliation SHA-256 `169df3171a84d724ca68394b385363062e15d919b3b4700b43fb42cd048658ce`.
- Попытка `a50f1e4a20a24721a43b43c2847395ee`: FAIL `fixture_observation_failed`, rows пустые, cleanup proven; SHA-256 `a70601cbaffdf40bf382051cc2c565dbeb4830b4767ac9656db9713ad2c2bef7`. Проверяющий запущен в Windows PowerShell 5.1 при использовании API PowerShell 7; до product attempt не дошёл.
- Текущий целевой набор: 137 PASS, `m1-s1-wip-dependent-09.xml`, SHA-256 `bb655c4994b070ad2f9263f7f77a8f6bdcb21ae8e63439a190e160e2771bd804`. Зависимые C5 runtime/ops: 56 PASS, `m1-s1-wip-dependent-c5ops-03.xml`, SHA-256 `8457a0909b4ff7a521e9d8f60cd52c51450fe3878a53198b6f1d554f2ef1a433`. Оба запуска — Windows identity владельца и отдельный pytest mutex namespace, без production/model/ASR.
- Отрицательная проверка WPS 5.1: run `2f0d0c98df5b49d1b61ed44fe0c7e372`, точный `fixture_runtime_unsupported` до регистрации; cleanup proven, tasks/processes отсутствуют; result SHA-256 `d380d8547b73352b1fa87de501c98b346a69d124f90d5a859262fca332ebda4b`.
- D01: прежние inventory/tool/requirements неизменны, 80 packages/15 pins/0 mismatch; inventory digest `c4b1be2c5795df1c19722441f157264ce7041558c616e26df98e67037c905be7`. OSV finding относится к pip 25.0.1 вне runtime Actions; пакеты не менялись.
- Security: повторный scoped scanner даёт тот же report SHA-256 `54d33ab1ef098a5d5b31a00f4ccfa793803fb81d950cee857ce8734eeb4192f8`: 42 findings, включая 6 synthetic fake-secret fixtures; новых findings в изменённых файлах нет. Классификация сохранена.

## Собранные замечания и ремонт

L1: FAIL из-за проверяющего, product blockers не найдено. L2/L3: FAIL/REWORK. Все обязательные замечания собраны до исправления: совместимость fixture с PowerShell, поздние child exits в cleanup, пропавший current при первой rotation/compaction/latch-clear failure, backup trigger в далёком будущем, частичная замена Scheduler tasks.

Пакет закрывает эти случаи целевыми тестами: типизированный отказ неподдерживаемой среды до регистрации; late Core/relay exit фиксируется до принадлежащего supervisor завершения; только exact authenticated latch позволяет материализовать control failure после прерванной rotation; backup start не позже ближайших локальных 03:30; installers проверяют старые XML/launcher digests, ставят задания disabled и при промежуточном отказе оставляют их отключёнными.

Инициализация/rebind/inspect/acknowledge допускают профиль всех трёх disabled заданий с теми же signatures под production mutex. Обычный run этот профиль отклоняет. После включения binding сохраняется. Смешанный профиль запрещён, кроме уже аутентифицированного backup перехода с disabled health. Staged backup получает ближайший будущий trigger, чтобы включение не проигрывало пропущенное время. Это минимальная правка безопасного переключения.

Необязательные P2 (дополнительные principal fields, усиление alert, детальные fixture substages, независимый parser auth) сохранены отдельно; точного нарушенного обязательного контракта в текущей области для них не установлено.

Шестой candidate `4777a2e…`, tree `723aa5cce3f7306e8b3fc1f8f9e3c4b150f79d67`, freeze SHA-256 `18caa7c1560befd71c32a9f1a6a69cf7cdf789217dd32de9ef75718dd4086aea`: реальные transient/budget/permanent случаи PASS (run `c8042392e9d94e6ea8d36cd80f4e694f`, result SHA-256 `02583d156083a8087843b99e20f8e560a6d7450e2a7fb2d85cd0b144549f00b4`; 2/3/1 attempts, LastTaskResult 0/23/29, cleanup proven). L1/L3 нашли две doc неточности; L2 также воспроизвёл потерю pre-signal Core exit и незавершённые current/.compact после rotation. Aggregate FAIL сохранён.

Пакет `fcf99fc…` сохраняет уже замеченный первым cleanup poll exit code. Только при exact authenticated latch и прежнем anchor zero/partial current либо фиксированный bounded .compact могут быть явно сверены владельцем; полный invalid, oversize, link, mismatch или отсутствие latch остаются STOP. .compact не становится историей: inspect не удаляет его, acknowledge сначала проверяет и удаляет только этот staging artifact, затем пишет typed control_failure/reset. Полный .compact дополнительно аутентифицируется и сравнивается с точными bootstrap/checkpoint semantics. Это завершение существующих файловых операций; Core до снятия latch не запускается.

RED: 10 воспроизведённых FAIL на новых границах; после ремонта целевые регрессии 15 PASS и общий затронутый supervisor/recovery/C5/ops набор **210 PASS**, `m1-s1-wip-final-02.xml`, SHA-256 `f71ff33cb1f2b2329abc11272915f403c5787ee3f8e51b290282f1f84daa5265`. Security `vibe-audit-wip-08.md` имеет тот же SHA-256 `54d33ab1…`. Исторические 218 и последующие 137+56 остаются привязаны к своим blobs; текущий код получает новое evidence.

Fresh LIVE inputs прочитаны **14.09, 21:30 МСК**, external `m1-s1-live-input-readback-20260914-2130.json`: config/doc11/assets/requirements/Python80/state/backup ownership совпали. Пять ASR files — 486214370 bytes; актуальный runtime digest `sha256:4b9a0e8e885f160af4d553283d1695d04c98eb083ce9dc1493d4cd219d7bc92b`. Старый `3bfe7656…` точно воспроизведён на тех же files при префиксе `sha256:` в member hashes: изменена сериализация evidence, не bytes. LIVE helper пока имеет принятые old bytes; candidate helper и новый config/launcher/task signatures связываются после staging. Этот readback закрывает прежний PENDING; перед activation изменения сверяются вновь.

## Исторические блокеры pre-freeze и согласованный порядок перехода

1. Проверить изменённые документы, записать одну внешнюю freeze-квитанцию итогового commit/tree/assets/config/input digests.
2. Выполнить three-case fixture этой revision через точный PowerShell 7: transient recovery, budget exhaustion, permanent STOP и доказанный cleanup. Использовать новый run id после сверки предыдущих effects.
3. Передать этот же freeze существующим L1/L2/L3 с прежними findings и применимым evidence. Собрать все verdicts; до aggregate PASS production закрыт.
4. Перед activation обновить LIVE inputs (readback 21:30 PASS, повторная сверка дельты перед activation), refs/status, backup и baseline. Выполнить разрешённые publication и переключение; проверить реальный результат/TXT и сохранность.
5. Только после фактической activation создать heartbeat этой же задачи: 72 часа включённого ПК, каждые 30 минут, минимум две плановые backup; gap >60 минут начинает окно заново; уведомления только об изменении/сбое/завершении. Автоматический restore/reset/restart heartbeat не выполняет.

Production-план: свежая проверенная v1.0.2 prechange generation; baseline tasks/receipts/offset. До первой mutation Gate operator сохраняет exact XML всех трёх задач, старые launcher/config bytes в приватный rollback-каталог через CreateNew, flush/fsync, SHA-256 и readback. Backup installer только сверяет переданный old XML digest; сохранение backup XML — ответственность Gate operator. Bot installer дополнительно сохраняет main/health XML и launcher.

Далее admission hold, штатный STOP и доказательство отсутствия exact процессов/Job/lease/listener; только три production task disabled. Опубликовать проверенный source через защищённую main без перемещения v1.0.2; clean LIVE на проверенном source. Staged main/health/backup получают candidate-bound config и точный readback; initialize/rebind выполняется при всех disabled. После этого включить задания и контролируемо запустить candidate backup cycle. Hold сохраняется до generation, повторной binding/STOP-проверки и аутентифицированного journal `restart_permitted`; затем существующий cycle выполняет `permit_admission → Enable/Start main → local/public readiness → Enable health`. Приём во время startup уже разрешён, поэтому post-baseline обязан учитывать все новые accepted tasks/receipts/offset, а не требовать неизменного числа 86. Ошибка start/readiness возвращает hold и scoped cleanup; ошибка внешней baseline-сверки требует той же безопасной остановки, без rollback БД.

После старта: один Core/Job/lease, local/public/stock readiness, одна квалификационная text-задача (model 1, ASR 0), правильный результат/TXT и post-baseline. Плановая пауза до 20 минут; при превышении остаётся STOP до диагностики. UNKNOWN эффект сначала сверяется. Rollback совместимых code/config/task bytes — по решению владельца; БД поверх новых accepted tasks не откатываются.

Разрешения владельца на необходимые действия и число запусков сохраняются; повторное подтверждение только из-за новой revision не требуется. Автоматический отказ среды фиксируется отдельно и не обходится.

Последний production read-only срез 14.09, 21:32 МСК: LIVE `82003c03…`, runtime DOWN; 86 tasks, 84 ACK receipts, 14/14 parts, четыре БД healthy, queue пустая, unknown=0, reconciliation=false, offset 375633467/revision 44146. External baseline `m1-s1-runtime-baseline-20260914-2132.json`. Backup exact v1.0.2 повторно проверен в 21:33: authentication/binding/ciphertext PASS, возраст 64966 с; перед switching создаётся отдельная prechange generation.

Раздельный verdict: published release — v1.0.2 unchanged; repaired candidate — проверенный код, финальный freeze/review pending; deployed runtime — без изменений, последний срез DOWN; stability observation — NOT STARTED; M2-G0 — BLOCKED.

## Архив предыдущих checkpoint

Ниже сохранена история прежних решений и проверок. Старые статусы и разрешения не заменяют текущий раздел и свежие внешние readbacks.

## Канонические refs и границы

| Объект | Значение |
|---|---|
| Published product/tag | `v1.0.2` → `82003c03d8a36015703472b472640ab4021fb416` |
| Remote main до M1-S1 | `88e58c8866db2384423f2b154df901a2e4af6c48` |
| LIVE | clean detached `Code/worktrees/telegram-live` на `82003c03…` |
| StateRoot / BackupRoot | canonical `.runtime/production-c6/migration-01/state` / `.runtime/production-c6/backups` |
| Ветка Gate | `codex/m1-s1-stability`, изолированный worktree |
| Текущий WIP | parent `e357629…`; exact candidate фиксируется только post-commit freeze receipt |

C6 не повторяется, MVP2 не запускался. Документ 11, исторические C6 receipts, sealed sources, старые backups и recovery refs не изменялись. Публикация и activation — разные статусы; tag v1.0.2 не перемещается.

## Свежий production-срез

Read-only проверка 14.09.2026, 13:57–13:59 МСК:

- main enabled/Running, LastTaskResult `267009`; legacy `RestartCount=10/PT1M` ещё действует;
- Health enabled/Ready/0; Backup enabled/Ready/0, daily 03:30 МСК;
- один logical supervisor (два venv host), два gated helper, один relay, одна Core chain; listener `127.0.0.1:8765` принадлежит Core;
- local readiness `true`, public readiness `true`;
- четыре БД healthy; 86 tasks/ingress, 168 audit events, 7 sealed answers, 84 ACK messages/receipts, 14/14 delivery parts;
- queue пустая, active job leases `0`, `delivery_unknown=0`, `reconciliation=false`;
- polling offset `375633467`, revision `43983`, один active polling lease; task/receipt/delivery counters не изменились;
- generation `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c`, manifest `sha256:575a2f272f7c48810fbb4c44d88215bcba2556dc01fb0c95a396c75ad93ae84e`: authentication/binding/ciphertext PASS, возраст `37840.017` с (<24 ч);
- restore не запускался.

Первая попытка проверки backup использовала неверный путь без `snapshot` и дала безопасный `backup_unverified`. После read-only inventory проверен правильный `snapshot/manifest.json`, получен PASS. Это ошибка диагностического пути, а не состояние копии.

Срез подтверждает доступность принятого runtime только на этот момент. Он не объясняет остановки 10–13 сентября, не доказывает recovery нового кандидата и не считается 72-часовой устойчивостью.

## Отклонённые снимки

1. `73ed1c95ff81f4c087bd7bc7e5d468e09cc8b1a6`, tree `2ca97f0a4b8a2a0fb6f534e211a636efe065c99c`: L1 FAIL, L2/L3 REWORK. Freeze receipt SHA-256 `90a20f87c36e8baf83fa166fcbedd1b8560001b361d9752cf664b86b05f2aaf8`.
2. `19c9bf3b790f411790191d58c6110817ae887d3f`, tree `340c37763e5164cb5163454d698d03ac90281a54`: L1 PASS, aggregate FAIL. Freeze receipt `m1-s1-source-freeze-19c9bf3.json`, SHA-256 `b0e449d82ec1404bfd6d864ac571f20dbdc841cddc5246b550d41634df8b404a`; review receipt `m1-s1-review-evidence-19c9bf3.json`, SHA-256 `a65bf4de927628d2a545cbe2ed27631265d4b005ec3d5d237830db9517e7b682`.
3. `121a4df400a6bed01427e48f9aa66eb2822852db`, tree `e35b662538aa5b6470eca4aea8356ef12286163f`: aggregate FAIL; freeze receipt SHA-256 `505749417eccdb67fe10ea87868b9d520547754b24c29519942ed93df3bb7663`.
4. `e357629859f728bf3403174a25a7a64c90d0d830`, tree `225a7000cc470e4bb011a4e3d5f7567182d17915`: L1 PASS, L2/L3 FAIL, aggregate FAIL; freeze receipt SHA-256 `930af8bd2aa57730015e413a99be2af1817e34ee11b6e76d8c6b52ce08540fc0`.

Evidence этих ревизий архивно и не переносится на новый candidate. Fixture `9af4c7e28d6b41d0a735e2f6b8c1934e` относится только к `19c9bf3…`: он доказал transient recovery и exhaustion, но не отдельную permanent ошибку.

## F01–F04 / D01

| ID | Класс | Состояние |
|---|---|---|
| F01 | FACT + UNKNOWN | Core/relay/simultaneous exit, local/public/both readiness, startup timeout, planned stop и cleanup различаются. Child exit после blocking probe теперь имеет приоритет. Исторический trigger 10–13 сентября остаётся `UNKNOWN` |
| F02 | FACT | Core JSON ≤4096 bytes и exact allowlist. History v3 хранит run/stage/error/exit, readiness, attempt/budget и cleanup; raw streams, argv/env, payload, task text и credential paths не сохраняются. Ранние CLI/control failures получают typed exit и bounded fallback receipt |
| F03 | FACT | Старый `RestartCount/PT1M` не перезапустил normal exit 23. Recovery остаётся внутри одного action, только после proven cleanup. Fixture v3 разделяет transient→attempt2, repeated transient→budget STOP attempt3 и permanent Core FAIL→один attempt/`stop_non_retryable`. Real Scheduler run нового freeze pending |
| F04 | FACT | Подготовленные docs01/CURRENT/runbook сохранены и включены. Документ 11 не редактировался: его digest теперь обязательный activation input |
| D01 | FACT + REVIEW | Python 3.12.14, 80 installed, 15 direct pins, 0 mismatch. OSV matches только у `pip 25.0.1`; pip не входит в runtime requirements/action. Install, upgrade, rebuild и package operations запрещены |

## Исправленный recovery-контракт

- `starting` записывается до проверки runtime inputs, Job API и operator log. После него есть exact terminal либо durable `control_failure`; ошибка history сохраняет класс `runtime_event_write_failed`.
- Terminal parser проверяет точную матрицу stage/error/status/child exit/readiness/count/outcome/cleanup.
- После каждого blocking readiness probe child проверяется снова; перед readiness terminal есть bounded propagation check.
- Каждая v3 запись аутентифицирована DPAPI текущего Windows owner и связана digest-chain. Checkpoint допустим только второй записью физического `.previous`, никогда в `current`.
- Reset требует exact newest authenticated digest. Отдельный owner-authenticated latch сохраняет pre-control failure до материализации в `control_failure`; потеря/подмена latch, сегмента, reparse, hardlink, extra/oversize/invalid file, append/fsync/rotation failure дают STOP.
- Operator log имеет fixed parser и current+previous по 5 MiB. Fallback CLI log — current+previous по 128 KiB, строка ≤2048 bytes, fixed schema и DPAPI authentication.
- Exit `70/71/72/73/74/75/76/77/78/79/80` различает create/signal/close/evidence, composition, activation binding, busy control, rejected reset, blocked history, startup и rebind.
- Retry разрешён только exact allowlisted transient после proven cleanup; permanent, missing/invalid outcome, cleanup/evidence failure, UNKNOWN и exhaustion дают STOP.

Trust boundary: Windows owner — control authority. DPAPI защищает от другого пользователя и offline-подделки; произвольный код того же owner уже имеет эквивалентный доступ к StateRoot/БД и вне этой границы. Core/relay не имеют команды reset; недоверенные Codex workers остаются в существующей sandbox/Job-изоляции. Секретный key file не создаётся.

Activation binding v3 включает source/code/schema, exact StateRoot, semantic flag, hashes документа 11, двух local config и Mini App assets, voice inventory, BackupRoot/ownership, Python/pythonw/base runtime и installed distributions/requirements, health launcher и фактические main/health/backup Scheduler signatures. Он также связывает principal SID, trigger identity/time и все влияющие task settings. Изменение любого input требует нового binding и явного bootstrap/rebind после сверки.

## WIP-проверки

- новый targeted supervisor/rework/L3 набор: `118 passed`;
- affected/dependent набор под реальной Windows identity и отдельным pytest mutex namespace: `218 passed`;
- sandbox-only identity mismatch воспроизведён отдельно; те же три проверки под владельцем: `3 passed`;
- Python AST, PowerShell parser, EVIDENCE JSON и `git diff --check`: PASS.

Real fixture новой ревизии, D01, security audit и L1/L2/L3 привязываются только к следующему source freeze. C0–C6 целиком не повторяются.

## Следующий checkpoint и production-план

1. Зафиксировать один source candidate и внешнюю receipt с commit/tree/source/assets/config/input digests.
2. На нём выполнить real Scheduler fixture v3, D01 без package operations, scoped security audit и независимые L1/L2/L3.
3. После aggregate PASS: fresh pre-change backup, baseline, exact XML/config export, planned stop exact supervisor/Job, свободные port/mutex/lease.
4. Опубликовать candidate через protected main, без нового tag и без перемещения v1.0.2.
5. Отключить остановленные exact задачи; заменить backup только через `-ReplaceExisting`, затем main/health, сделать readback; переключить LIVE на exact reviewed source commit и candidate-bound config.
6. При остановленном runtime выполнить explicit initialization полного activation binding; candidate backup cycle запускает ровно один runtime.
7. Проверить один Core/Job/lease, local/public/stock readiness; одну разрешённую text-задачу, результат/TXT и post-baseline. UNKNOWN сначала сверяется, blind retry запрещён.

Бюджеты: одна activation, одна реальная text-задача, максимум один model execution, ASR `0`. Ожидаемая пауза ≤15 минут; через 20 минут без сигнала — STOP/diagnosis. Rollback только совместимого code/config; БД не откатываются поверх новых accepted tasks.

## Согласованное наблюдение

После T0 эта же задача создаёт heartbeat каждые 30 минут. Он только читает Scheduler, authenticated history/fallback, readiness, exact process/listener/lease, DB counters и backup manifests; auto restart/reset/restore отсутствует.

PASS требует непрерывных 72 часов включённого ПК и owner session, минимум двух planned daily backup с LastTaskResult 0 и authentication/binding/ciphertext PASS, отсутствия необъяснённых terminal events, одного runtime и сохранности данных. Gap >60 минут начинает окно заново. Старый 15-минутный smoke не считается устойчивостью.

## Раздельный verdict

| Слой | Статус |
|---|---|
| Published release | v1.0.2 / `82003c03…` неизменён |
| Repaired candidate | WIP GREEN; source freeze/reviews pending |
| Deployed runtime | accepted `82003c03…`, currently DOWN |
| Stability observation | AGREED, NOT STARTED |
| M2-G0 | BLOCKED |

## Архив состояния до отклонения `19c9bf3…`


**Текущий статус 14.09.2026, 12:28 МСК:** замечания по первой отклонённой ревизии собраны и исправлены одним WIP-пакетом. Implementation checkpoint `87dba94ab340f5b335f0779043c948b7ac5671b3`, tree `3a5408aa630070f247f5b3069311cd08585b4a0a` локально GREEN. Единственный новый Gate freeze, реальный Scheduler fixture v2 и независимые L1/L2/L3 ещё не выполнены. Принятый v1.0.2 остаётся в LIVE; это не PASS 72-часового наблюдения.

## Текущий checkpoint после rework

Freeze `73ed1c95ff81f4c087bd7bc7e5d468e09cc8b1a6` / tree `2ca97f0a4b8a2a0fb6f534e211a636efe065c99c` отклонён: L1 `FAIL`, L2/L3 `REWORK`. Его нельзя публиковать, развёртывать или смешивать с доказательствами нового кандидата. Внешняя квитанция этой ревизии сохраняется с SHA-256 `90a20f87c36e8baf83fa166fcbedd1b8560001b361d9752cf664b86b05f2aaf8`.

Все замечания первой ревизии были собраны до пакетных исправлений. Закрыты: privacy temp path; гонка planned stop/Core exit; общий local/public probe slot; сброс STOP удалением recovery history; неустойчивые control failures; неполный fixture; safe-shaped вместо exact Core allowlist; retry без точного `STOPPED`; отсутствие полной hash/transition chain; raw health redirects; parser/D01 и stale active docs.

Новый стабильный freeze id — `a8e7a1f0330f4f889263ed2751d3eee8`. Самоссылочный commit нельзя включить в собственные bytes, поэтому этот документ хранит exact implementation checkpoint, а commit/tree/source/assets/config/input digests следующего документационного commit будут один раз записаны во внешнюю post-commit квитанцию с этим id. Только эта ревизия получит реальный Scheduler fixture v2 и L1/L2/L3.

### Актуальный production-срез

Read-only срез 14.09.2026, 12:20–12:26 МСК:

- LIVE clean detached на `82003c03d8a36015703472b472640ab4021fb416`; `origin/main` — `88e58c8866db2384423f2b154df901a2e4af6c48`;
- main enabled/Running с 03:31:05 МСК, LastTaskResult `267009`, legacy `RestartCount=10/PT1M`; Health Ready/0 в 12:20:44 МСК; Backup Ready/0, следующий запуск 15.09 в 03:30 МСК;
- один logical supervisor (venv host+child), два gated helper, один relay, один Core chain, один listener `127.0.0.1:8765` и один active polling lease;
- read-only probe вне сетевого sandbox: `local_ready=true`, `public_ready=true`; sandbox-only public FAIL отброшен как ограничение инструментальной сети, а не production факт;
- четыре БД healthy; 86 tasks/ingress, 168 audit events, 7 sealed answers, 84 ACK messages/receipts, 14/14 delivery parts; queue пустая, active job leases `0`, delivery unknown `0`, reconciliation `false`;
- offset `375633467` не уменьшился, revision вырос до `43607`; tasks/receipts не изменились;
- generation `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c`, manifest `sha256:575a2f272f7c48810fbb4c44d88215bcba2556dc01fb0c95a396c75ad93ae84e`, authentication/binding/ciphertext PASS, возраст `32082.868` с. Restore не запускался.

Эти факты подтверждают доступность принятого runtime на момент среза, но не объясняют остановки и не доказывают recovery или 72 часа.

### F01–F04 / D01

| ID | Текущее состояние |
|---|---|
| F01 | Core/relay/simultaneous exit, local/public/both readiness, startup timeout, planned stop и cleanup различаются. Исторический trigger 10–13 сентября остаётся `UNKNOWN` |
| F02 | Локально repaired: exact Core failure allowlist, один ASCII JSON ≤4096 bytes, no raw persistence; `nobus-runtime-event-3` хранит binding, linked digests, run/stage/error/exit, local/public, attempt/budget и cleanup |
| F03 | Локально repaired, но real v2 pending: один Scheduler action, budget `10 retries / 60 s / 11 total`, retry только после proven cleanup; missing/invalid/binding mismatch, UNKNOWN, permanent и exhaustion дают STOP |
| F04 | docs01/CURRENT/runbook входят в пакет; документ 11, C6 receipts и sealed sources не менялись |
| D01 | Local inventory проверяет actual environment, exact pins и duplicate inputs. Frozen network metadata query ещё не выполнен; install/upgrade не выполнялись |

История recovery находится только в `<StateRoot>/supervisor-control`. Первый запуск требует отдельного `--initialize-recovery` под production mutex. Каждая v3 запись связана с предыдущей; reset требует exact newest digest. Ротация — current+previous по 1 MiB, строка ≤2048 bytes; отсутствие любого сегмента после ротации, лишний/reparse/oversize файл, parser/write/fsync/rotation error блокируют запуск. Fixed operator log также ограничен двумя файлами по 5 MiB. Exit `70/71/72/73` различает create/signal/close/evidence failure. Child exit проверяется раньше planned stop; permanent Core FAIL и invalid/missing outcome побеждают retry.

In-place backup/restore меняет только четыре БД, поэтому control history сохраняется. Если StateRoot реконструирован или control directory утрачен, обычный start даёт STOP; bootstrap новой binding разрешён только после сверки данных/effects. Удаление истории не является reset.

### Текущие проверки

- initial rework RED: `13 failed`;
- расширенная rework-матрица: `24 passed`;
- затронутый набор C5 runtime + M1-S1: `116 passed in 18.60s`;
- зависимые host-context tests: `34 passed in 32.35s` с отдельными mutex/temp roots;
- Python AST, PowerShell parser и `git diff --check`: PASS; C0–C6 целиком не повторялись.

### Следующая точная проверка

После commit документационного checkpoint внешняя квитанция фиксирует единственную Gate revision. Fixture v2 создаёт ровно два уникальных one-time tasks с canonical `pythonw`, Interactive/Limited, `IgnoreNew`, Scheduler restart count `0`. Transient обязан завершиться на attempt 2 / LastTaskResult 0; permanent — на attempt 3 / budget STOP / LastTaskResult 23 и без четвёртой попытки 75 секунд. Result включает controller/probe digests, hashes v3/operator segments, финальные attempt/budget/disposition/cleanup и proven удаление tasks. Та же frozen revision проходит D01 metadata и scoped static/manual security audit без установки пакетов; затем L1/L2/L3 проверяют этот же commit.

### Production и 72 часа

После PASS reviewers: fresh backup → baseline → штатная остановка exact Job → свободные port/mutex/lease → exact LIVE checkout → Tasks с Scheduler retry `0` → recovery bootstrap → один start → local/public/stock readiness → одна text-задача и TXT → post-baseline. Бюджеты: одна activation; одна text-задача и максимум одно model execution; ASR `0`; UNKNOWN сначала сверяется; БД не откатываются. Ожидаемая пауза до 15 минут, после 20 минут без проверяемого сигнала — STOP и диагностика.

После фактического T0 heartbeat этой же задачи каждые 30 минут только читает Scheduler, v3, readiness, singleton/process/listener/lease, DB counters и backup manifests. Никакого auto reset/restore/restart. PASS требует непрерывные 72 часа включённого ПК/owner session, минимум два planned backup с LastTaskResult 0 и повторной authentication/binding/ciphertext проверкой, один runtime и сохранность данных. Разрыв более 60 минут запускает окно заново. Старый 15-минутный smoke не считается устойчивостью.

Раздельный verdict: published release — `v1.0.2` неизменён; repaired candidate — implementation GREEN, freeze/reviews pending; deployed runtime — прежний `82003c03`; observation — NOT STARTED; M2-G0 — BLOCKED.

## Архив первой отклонённой ревизии

Весь текст ниже — сохранённый pre-freeze record `73ed1c9`. Он нужен для истории RED/diagnosis, но его утверждения о «исправленном реальном fixture» не являются доказательством новой revision.

### Архив: результат pre-freeze этапа

Исторический первичный триггер остановок 10–13 сентября восстановить нельзя: он остаётся `UNKNOWN`. Отдельно воспроизведена причина отсутствия recovery: на этом хосте `RestartCount/PT1M` не перезапустил нормально стартовавший `pythonw` после exit 23. Обе fixture-задачи выполнились ровно один раз и были удалены; исчерпание production-бюджета по-прежнему не заявляется.

Локальный repair сохраняет строгий безопасный JSON Core и отдельные типизированные причины, а ограниченную серию retry выполняет внутри одного Scheduler action после доказанного cleanup. Реальный fixture подтвердил recovery transient-сбоя на второй попытке и постоянный STOP после исчерпания трёх попыток без четвёртого запуска. Затронутые наборы — 49, 134 и 88 PASS. Сетевой D01 выполнен один раз; matches относятся только к установленному `pip 25.0.1`, пакеты не менялись.

### Архив: контракт Gate

- Восстановить один принятый MVP1 без повторения C6 и без работ MVP2.
- Сохранить Core authority, четыре канонические БД, receipts, polling offset, idempotency и `UNKNOWN/reconciliation`.
- Не создавать второй Core, очередь или blind retry; не восстанавливать БД поверх новых принятых данных.
- До production предъявить один revision-bound пакет с точными Actions/config/input digests, backup, baseline, бюджетами, паузой и rollback.
- Разделять published release, repaired candidate, deployed runtime и завершённое 72-часовое наблюдение.

### Архив: исходные refs

| Объект | Значение |
|---|---|
| Base/main | `88e58c8866db2384423f2b154df901a2e4af6c48` |
| Published product v1.0.2 | `82003c03d8a36015703472b472640ab4021fb416` |
| Annotated tag object | `59952c44118606c26e34e20a39ed88ef5c686620` |
| Product tree | `78d47a3be446d33a2ace24144b75d7221f73009e` |
| Main tree | `800e999dc9f24e90808a4784b90bf44d00a72cb1` |
| Рабочая ветка | `codex/m1-s1-stability`, изолированный worktree от exact main |
| Candidate commit/tree | отсутствует: freeze выполняется один раз после закрытия F03/D01 |

Канонический checkout имел пользовательский docs WIP и не изменялся. LIVE остаётся clean detached на product commit. Исторические C6 receipts, sealed sources, документ 11, backups и recovery refs не изменялись.

Контекст Nobus Memory читался только в `project:nobus-space`. Попытка создать managed pointer на этот checkpoint завершилась `ARGUMENT_REJECTED`; запись не произошла, повтор без новой гипотезы не выполнялся. Доступность хранилища из этого не выводится и работа Gate не блокируется.

### Архив: F01–F04 и D01

| ID | Класс | Состояние | Факт и остаток |
|---|---|---|---|
| F01 | FACT + UNKNOWN | DIAGNOSED / historical trigger UNKNOWN | Детерминированно различаются Core/relay exit, startup deadline, local/public/both readiness failure, planned stop и cleanup. Точный trigger старых остановок не выводится по аналогии |
| F02 | FACT | LOCAL REPAIR GREEN / NOT DEPLOYED | Строгий parser безопасного Core JSON, bounded capture, schema `nobus-runtime-event-2`, ротация и fail-closed write/history. Raw stdout/stderr, argv/env, payload и credentials не сохраняются |
| F03 | FACT | OLD MECHANISM FAIL / REPAIRED MECHANISM REAL PASS | `RestartOnFailure` для normal action exit 23 не сработал. Один Scheduler-hosted candidate controller реально восстановил transient на attempt 2 и остановил permanent на attempt 3 по бюджету; cleanup proven |
| F04 | FACT | LOCAL FIX INCLUDED / NOT PUBLISHED | Подготовленные docs01/CURRENT/runbook сохранены и актуализированы по новым фактам. Документ 11 и исторические C6 sources не менялись; публикации нет |
| D01 | FACT | REVIEW_TOOLING | Python 3.12.14, 80 пакетов, 15/15 direct pins, `pip check` PASS. Один OSV query выполнен; matches относятся только к `pip 25.0.1`. Обновления и установки не выполнялись |

### Архив: read-only production evidence

Последнее цельное наблюдение: 14.09.2026, 08:28–08:31 МСК.

- LIVE — прежний `82003c03`; candidate не развёрнут.
- `NobusSpaceBot`: enabled / Running, LastRun 03:31:05 МСК, LastTaskResult `267009` (running). Legacy settings всё ещё `RestartCount=10/PT1M`; definition digest не изменился: `sha256:f68400b92c7dbc94e6116c7f616f9d3ea4473a50ace5e94ea3b70deb1eabfa80`.
- Один логический supervisor (два `pythonw` action-host из-за venv redirector), два gated helpers, один relay, один Core-владелец listener и один listener 8765.
- `local_ready=true`, `public_ready=true`. Health завершился Ready / LastTaskResult 0 в 08:28:44 МСК.
- Backup завершился LastTaskResult 0; новое поколение `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c` прошло ownership, latest pointer, generation inventory, authenticated manifest, target binding, freshness и ciphertext hashes. Следующая копия — 15.09 в 03:30 МСК; restore не запускался.
- Запуск main через 65 секунд после начала backup соответствует штатному backup restart path; это вывод по времени и коду цикла, а не доказательство `RestartOnFailure`.
- Legacy log дополнился только `starting` в 03:31:06 МСК; последний terminal — `runtime_failed` 13.09 в 13:28:54 МСК. V2 log отсутствует, что ожидаемо до deploy.

Baseline после автозапуска:

- 86 task snapshots и ingress claims, 168 audit events, 7 sealed answers;
- 84 outbox messages `acked`, 84 `ack` receipts, 14/14 delivery parts подтверждены;
- Telegram jobs/очередь пусты, active job leases 0, delivery unknown 0, reconciliation false;
- один active polling lease; offset `375633467`, revision `42685`;
- по сравнению с baseline 13.09 задачи/receipts/delivery не изменились, offset монотонно вырос с `375633465` на 2. Дублей или второй очереди не обнаружено.

Текущая доступность принятого runtime — факт, но не закрытие M1-S1: controlled candidate launch, реальный результат/TXT и 72 часа ещё не выполнялись.

### Архив: локальный repaired WIP

`scripts/run_nobus_space_live.py`:

- читает только один завершённый ASCII JSON Core до 4096 байт; лишние поля, повторные ключи, неверный framing, unsafe code и переполнение отвергаются;
- stderr по-прежнему уходит в `DEVNULL`; stdout Core только дренируется bounded parser, сырой текст не сохраняется;
- пишет schema `nobus-runtime-event-2`: JSONL не более 2048 байт на запись, current не более 1 MiB и один `.previous`; symlink/junction/не-файл и ошибка записи дают STOP;
- различает Core, relay, одновременный child exit, startup timeout, local/public/both readiness, planned stop и cleanup outcome;
- сохраняет обе readiness-проверки без short-circuit, `series_id`, `run_id`, exact attempt/budget и cleanup outcome;
- retry разрешён только для relay exit после steady, public fail при local PASS, startup timeout при local PASS/public FAIL и safe Core `telegram_unavailable`; все остальное даёт типизированный STOP;
- `starting` без terminal блокирует новый запуск как `previous_attempt_unknown`; exact terminal retry продолжает тот же series. `--inspect-recovery` только читает, а exact-digest reset сам runtime не запускает.

Gate-only инструменты не входят в production action:

- `tests/gate_m1_s1/collect_runtime_baseline.py` — defensive SQLite `mode=ro`, только агрегаты/offset/digests;
- `tests/gate_m1_s1/audit_dependencies_osv.py` — без флага выполняет только локальный inventory; сеть возможна только с `--query-osv` на один фиксированный endpoint;
- `tests/gate_m1_s1/Invoke-SchedulerRetryFixture.ps1` и `tests/fixtures/m1_scheduler_exit_probe.py` — два уникальных synthetic tasks, без production input, stdout/stderr и event logs; candidate-owned controller запускается как один реальный Scheduler action.

### Архив: проверки pre-freeze WIP

- Исходный RED: 23 ожидаемых отказа новых F02-тестов до реализации.
- Реальный изолированный Windows Job доказал `gated helper → child exit 23` и передачу одного безопасного JSON.
- Реальный старый F03 mechanism: FAIL `scheduler_restart_contract_not_observed`, cleanup proven.
- Реальный исправленный F03 mechanism: PASS; transient attempts `1→2`, permanent attempts `1→2→3 budget_exhausted`, 75 секунд без лишней попытки, cleanup proven.
- Дополнительный RED на fail-closed recovery semantics: 4 отказа; после исправления M1-S1 файл — `49 passed`.
- Единый затронутый набор supervisor/readiness/Windows SSH/installer/maintenance — `134 passed in 56.70s` при работающем production и отдельных test mutex.
- Все зависимые runtime-maintenance и backup-recovery тесты — `88 passed in 107.33s`; одна существующая deprecation warning, установок нет.
- Прежние `76 passed` и 11 supervisor/readiness проверок сохранены; C0–C6 целиком не повторялись.
- PowerShell parser трёх затронутых scripts, Python AST, `git diff --check`, `pip check` и относительные Markdown-ссылки — PASS.

Это WIP evidence, а не L1/L2/L3. Независимые L1/L2/L3 выполняются только после одного freeze целого кандидата; evidence разных bytes смешивать нельзя.

### Архив: реальный F03 FAIL, сохранённый без повторения

Разрешённый run `1a45b43f98e84558b3695b7371ad9b7e` создал только `NobusSpace-M1S1-Fixture-Transient-1a45b43f` и `NobusSpace-M1S1-Fixture-Permanent-1a45b43f`. Обе задачи стартовали 14.09 в 07:30:49 МСК, записали только attempt 1 / `retryable_failure` / exit 23 и остались Ready с LastTaskResult 23. Ни через две минуты, ни в дополнительном 75-секундном окне повторов не было.

Cleanup — `proven`; в 07:47:05 МСК оба имени повторно подтверждены отсутствующими. `result.json`: 1296 bytes, SHA-256 `33bcfbe35fa8b0c6a7a26412f4941879ec2fa79eed7e0e44c49b2e4f4a17b6fa`; оба JSONL: 203 bytes, SHA-256 `763c4efe054f8fb3f6e21989272293635851276add203c887ded7b95c9e19f78`.

[Схема Microsoft RestartOnFailure](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-restartonfailure-settingstype-element) описывает Count/Interval. [Протокольное описание Microsoft](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-tsch/2ff4aa5a-7bc4-449f-bbb1-27475645867f) связывает повтор с невыполненными условиями запуска или невозможностью запустить action; оно не обещает повтор любого уже стартовавшего процесса после обычного ненулевого exit. Локальный fixture подтверждает фактическое поведение этого хоста.

### Архив: D01 advisory metadata

Один разрешённый POST к `https://api.osv.dev/v1/querybatch` передал только 80 public name/version пар. Inventory digest: `sha256:c4b1be2c5795df1c19722441f157264ce7041558c616e26df98e67037c905be7`. OSV вернул шесть advisory families для `pip 25.0.1`: [GHSA-4xh5-x5gv-qwph](https://github.com/advisories/GHSA-4xh5-x5gv-qwph), [GHSA-6vgw-5pg2-w6jp](https://github.com/advisories/GHSA-6vgw-5pg2-w6jp), [GHSA-58qw-9mgm-455v](https://github.com/advisories/GHSA-58qw-9mgm-455v), [GHSA-jp4c-xjxw-mgf9](https://github.com/advisories/GHSA-jp4c-xjxw-mgf9), [GHSA-wf93-45jw-7689](https://github.com/advisories/GHSA-wf93-45jw-7689) и [GHSA-qwm4-qh6w-59xr](https://github.com/advisories/GHSA-qwm4-qh6w-59xr). Последний исправлен в 26.2.0. Structured result — `REVIEW`; внешний wrapper сообщил exit 1 вместо предусмотренного скриптом exit 2 для matches. Причина этого расхождения остаётся `UNKNOWN`; запрос не повторялся.

Production action не импортирует и не запускает `pip`; в `requirements.txt` его нет. Verifier lock всё ещё содержит `pip==26.1.2`, поэтому до любого нового install/rebuild нужны exact version/hash review и отдельное разрешение. В этом Gate пакеты не менялись.

### Архив: непригодный как Gate evidence F03 fixture v1

Разрешённый run завершён; bounded evidence сохранено, оба временных задания удалены и отдельно подтверждены отсутствующими в 09:26:51 МСК.

| Поле | Значение |
|---|---|
| Run id | `762a5aaeb35546d1be51b0febf576bf5` |
| Transient task | `NobusSpace-M1S1-Fixture-Transient-762a5aae` |
| Permanent task | `NobusSpace-M1S1-Fixture-Permanent-762a5aae` |
| Fixture script SHA-256 | `17a5b17848c8b5e1255d74a321791ca14a1d1b386d9d6d2177350d4c2d891563` |
| Probe SHA-256 | `4160ff69fd5040716282c7ad5cca85e111cc89662c0b9f8a7e1c2d7df49b0167` |
| Product controller SHA-256 | `77ea03f5a41ea09a8a622c03d040aefbe758d806efa0909b97ce342f381612c6` |
| Result | `PASS`, 1614 bytes, `sha256:36cd9c1ad73484161bceff9a58140e4cb6998baea132e63320a1a4eb670919a6` |
| Transient receipt | attempts 1 retryable / 2 recovered; 397 bytes, `sha256:36ccdf621955112ea3dd8f47e7dec976cc61a9770b2d1683c21d19b31cb67dee` |
| Permanent receipt | attempts 1/2 retryable / 3 budget exhausted; 608 bytes, `sha256:d9af5102789f8edbaf46f9a633f5ace3184a584876270129b6ec74fadeeb5499` |

Один разрешённый вызов зарегистрировал ровно эти два one-time tasks с canonical `pythonw`, Interactive/Limited и `IgnoreNew`, без Scheduler restart settings. Scheduler запустил один candidate controller: transient восстановился на attempt 2 после 60 секунд, permanent завершился budget STOP после трёх total attempts. Дополнительные 75 секунд подтвердили отсутствие четвёртой попытки. Production task, StateRoot, модель, ASR, порты, сеть, messages и event logs не использовались.

Следующий шаг: один freeze commit/tree/source/assets/config/input digests → обязательные независимые L1/L2/L3 ровно этой ревизии → единый production plan → публикация, deploy, Task definitions, controlled start, одна реальная text-задача и TXT в пределах текущего разрешения. Блокирующие reviewer findings сначала собираются и только затем исправляются одним пакетом.

### Архив: критерий 72-часового наблюдения

Владелец согласовал критерий 14.09. После разрешённой активации heartbeat этой же задачи каждые 30 минут только читает Scheduler, structured events, local/public readiness, singleton/process/lease counts, safe DB health и backup manifests. Автоматика пока не создана.

Критерий PASS:

- нет необъяснённых terminal events; каждый planned stop, transient recovery или bounded STOP имеет run id, причину, attempt/budget и cleanup;
- вне планового backup local/public готовы; плановая пауза backup не более 10 минут и явно связана с его run;
- всегда не более одного supervisor/Core/relay/listener/polling lease, нет второй очереди и `delivery_unknown/reconciliation`;
- минимум два плановых backup с LastTaskResult 0 и повторной authentication/binding/ciphertext проверкой;
- начальный и конечный baseline подтверждают сохранность старых tasks/receipts и монотонный offset, а одна разрешённая новая задача имеет ровно один intake/result/TXT;
- любой разрыв наблюдения более 60 минут, выключение ПК или потеря owner session не считается PASS: окно начинается заново после сверки состояния.

Автоматика создаётся только после отдельного разрешения и точного T0/T72. Старый 15-минутный smoke не используется как доказательство устойчивости.

### Архив: прежний раздельный verdict

| Уровень | Verdict |
|---|---|
| Published release | `v1.0.2` / `82003c03` — ACCEPTED / PUBLISHED |
| Repaired candidate | READY FOR FREEZE; LOCAL GREEN / REAL SCHEDULER-HOSTED FIXTURE PASS |
| Deployed runtime | Candidate NOT DEPLOYED; прежний v1.0.2 сейчас READY |
| Stability observation | AGREED / NOT STARTED; automation NOT CREATED |
| M2-G0 | BLOCKED до полного PASS M1-S1 и отдельного решения владельца |
