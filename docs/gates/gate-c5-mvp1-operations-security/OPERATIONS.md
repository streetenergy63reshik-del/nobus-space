# C5 — запуск, остановка и диагностика

Этот документ связывает эксплуатационные изменения и локальные проверки C5.
Окончательные source/package revisions и независимые решения находятся в
[ACCEPTANCE](ACCEPTANCE.md); проверенные файлы и сохранённые receipts — в
[RUNTIME-RECEIPTS](RUNTIME-RECEIPTS.json). До фиксации общей revision используется
`WIPcode_digest`, вычисленный из списка SHA-256 исходных файлов. Он не включает
сам документ или receipt и не создаёт самоссылочного хеша.

Код C4 сохранён в пределах контракта: один Core и durable admission/state,
подтверждаемый голос, одноразовые owner-bound callbacks, request reconciliation,
единый результат и TXT, отдельные UNKNOWN provider/delivery outcomes. Реальную
приёмку C4 и model/ASR-вызовы эти проверки не повторяют.

## Что изменилось

| Обязательство | Реализация C5 | Проверка |
|---|---|---|
| Один supervisor и poller | Отдельный глобальный mutex supervisor; прежний mutex Core и generation-bound polling lease сохранены | Реальный duplicate start с синтетическим именем отклонён; после выхода mutex доступен; просроченная lease не меняет checkpoint |
| Процесс не выходит из своего Job | Базовый Python ждёт named event; только после Job assignment запускает Core/relay; event живёт до выхода helper | Нативный порядок assign → release; инвентаризация всех членов Job, включая conhost; PID и время создания связаны с открытыми handles |
| Штатная остановка | `--stop` сигналит точный локальный named event; supervisor передаёт stop/EOF по анонимному stdin; Core сначала закрывает admission и durable workers | Реальный graceful stop; повторная отмена вызывающей coroutine не обрывает cleanup; затем Job ActiveProcesses=0 |
| Аварийная остановка | Завершается только Job, созданный этим supervisor; ошибки setup/cleanup не дают успешный статус | Проверены Job terminate и kill-on-close; подтверждено завершение всех открытых handles; восемь негативных setup/cleanup сценариев |
| Конечные перезапуски | Supervisor не создаёт собственный цикл restart; Health task только наблюдает; Scheduler сохраняет RestartCount=10 | Проверены исходники installer и отказ повторно стартовать через Health |
| Правдивая готовность | Старт проверяет полный набор store и restore hold до worker/ASR probes; локальная readiness требует Core/queue/worker, доступного ASR и свежего polling; supervisor и Health launcher проверяют HTTP200 и точное тело локальной и публичной readiness | Неподготовленный store и restore hold запрещают запуск; закрытый/упавший ASR не готов; HTTP403 или чужое тело не считаются ready |
| Версия исполнителя | Production принимает только bundled `codex-cli 0.144.4`; discovery установленного CLI доступен лишь через явный developer argument | Отсутствующий bundle и другая версия fail closed без поиска в PATH/VS Code |
| Секреты и stdout | Дочерние процессы получают ограниченный набор environment keys; access log и сырые stdout/stderr Core/relay не публикуются; supervisor пишет только фиксированные события | Проверены исключённые ambient variables и отсутствие stderr forwarding; сообщения ошибок используют безопасные коды |

Контроль `--stop` относится к новому supervisor. Он не останавливает старый или
чужой runtime по имени процесса. Если control event отсутствует, команда
завершается неуспешно. Принудительная остановка старого Scheduler/service не
была частью C5.

## Пределы

- Startup — до 360 секунд. Штатный Core shutdown — до 90 секунд, затем только
  собственный Job; ожидание нулевого числа процессов Job — ещё до 10 секунд.
  Ошибка очистки даёт failure и требует проверки владельцем.
- После готовности supervisor делает проверку через каждые 10 секунд; три
  последовательных отказа завершают текущий runtime. Один локальный probe имеет
  timeout 2 секунды, публичный — 5 секунд, поэтому период включает время probe.
  Внешняя недоступность не запускает бесконечные внутренние попытки.
- Polling readiness допускает не более 90 секунд после последнего успешного
  batch. Lease 240 секунд и её fencing сохраняются. Готовность локального worker
  не обещает успешный следующий ответ внешнего model provider.
- После 60 секунд простоя ASR намеренно освобождает память и остаётся доступным
  для запуска по запросу. Это отдельно от failed/closed child; потеря обязательного
  процесса при работе делает dependency unavailable. Новый model artifact не скачивается.
- HTTP слушает только loopback. Uvicorn: максимум 16 соединений, backlog 32,
  keep-alive 5 секунд, incomplete h11 event 16 KiB, graceful shutdown 10 секунд,
  WebSocket выключен, `proxy_headers=False`.
- HTTP boundary: заголовки до 16 KiB и 64 полей; header deadline 5 секунд;
  path/query до 512 байт; до 8 активных ASGI requests; общий deadline 90 секунд;
  ответ до 1 MiB. Общий бюджет 120 запросов/минуту с burst 30, session budget
  30/минуту с burst 10. Это общие ограничения локального owner-bound приложения,
  а не доверие к клиентскому `X-Forwarded-For`.

Полная ingress/security матрица относится к отдельным HTTP tests и общей
приёмке C5. Этот документ связывает server configuration; наличие этих limits
в source не доказывает включённую защиту публичного live endpoint.

## Подготовленная композиция C6

Глобальный `_GATE_C1_SEMANTIC_ADMISSION_ENABLED` остаётся `False`. Только явный
`--semantic-admission` включает принятую смысловую цепочку в конкретном запуске.
`--runtime-root` задаёт отдельные state/temp/artifact directories, а
`--voice-model-directory` — уже подготовленный и проверенный local ASR artifact.
Owner binding читается из прежнего точного локального файла выбранного checkout;
credentials остаются в существующем Windows credential store.

В installer добавлены три необязательных параметра:

| Параметр installer | Передаваемый аргумент supervisor |
|---|---|
| `-SemanticAdmission` | `--semantic-admission` |
| `-StateRoot` | `--runtime-root` |
| `-VoiceModelDirectory` | `--voice-model-directory` |

State/model directories должны уже существовать, быть абсолютными локальными
путями без reparse points в цепочке родителей. Отсутствующий switch сохраняет
semantic OFF. Health launcher использует тот же StateRoot через `--runtime`.
Прежний `-RuntimeRoot` выбирает каталог установленного Python/logs и не подменяет
`-StateRoot`. Проверка параметров и `-WhatIf` не меняют Scheduler.

После отдельного разрешения C6 владелец задаёт точные значения переменных,
проверяет accepted checkout, backup и текущую identity, затем просматривает план:

```powershell
.\ops\windows\Install-NobusSpaceBot.ps1 `
  -RepositoryRoot $acceptedCheckout -RuntimeRoot $runtimeOwner `
  -SemanticAdmission -StateRoot $stateRoot -VoiceModelDirectory $qualifiedModel `
  -WhatIf
```

Фактическая установка и активация в C5 не выполнялись. Команда штатной остановки
уже нового supervisor после его отдельной активации:

```powershell
& $python .\scripts\run_nobus_space_live.py --stop
```

`stop_requested` означает доставленный локальный сигнал. Завершение подтверждают
после выхода supervisor, освобождения порта и отсутствия его process tree.
Ошибка или истёкший deadline требуют сверки; нельзя объявлять cleanup успешным
по одному ответу команды.

Restore всегда оставляет durable reconciliation hold. Пока отдельно не сверены
watermark, новые accepted данные и внешние effects, startup и новые сессии
заблокированы. Автоматического снятия hold и live restore в C5 нет. Отдельные
RPO/RTO/backup/retention факты находятся в storage receipts и общей приёмке.

## Воспроизводимость и границы доказательства

Из принятого checkout, установленным закреплённым Python, на Windows:

```powershell
$env:NOBUS_C5_RUNTIME_RECEIPTS='1'
$drillParent = Join-Path $PWD '.runtime/c5/drills'
New-Item -ItemType Directory -Force -Path $drillParent | Out-Null
$drillRoot = Join-Path $drillParent ([guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $drillRoot) { throw 'Drill target already exists' }
& $python -m pytest tests/test_c5_runtime_operations.py `
  tests/test_telegram_mvp1_runner.py tests/test_live_supervisor.py `
  tests/test_ops_queue1.py --basetemp $drillRoot -q --disable-warnings
```

Тесты используют synthetic input, временные SQLite/marker fixtures и собственные
Windows Jobs. Сеть, credentials, реальные model/ASR inference и live Scheduler
не вызываются. Инвентаризация Job берётся из Windows API: она не предполагает,
что число процессов заранее равно трём. Для каждого члена фиксируется открытый
handle, PID и время создания; после завершения handles signaled. Для terminate
и полного штатного cleanup отдельно измерен `ActiveProcesses=0`.

Авторские целевые результаты: 60 runtime/supervisor checks и 13 operational
checks PASS; compile и PowerShell parse PASS. Это не независимый L2/L3 и не
замена общего regression кандидата. Первоначальные FAIL сохранены: гонка
времени жизни startup event, две ошибки предположений verifier о conhost и
отдельный stale bytecode случай во время изменения storage schema. Новые PASS
не переименовывают старые результаты. При подготовке независимой проверки
дополнительно воспроизведены пять FAIL: обход исходного reparse path до resolve
и Health HTTP200 с чужим телом. Оба дефекта исправлены; общий целевой набор
из 73 проверок прошёл. Первый прогон этих негативных проверок также сохранил
четыре ошибки setup из-за отсутствия родительского каталога временных файлов.

По read-only preflight основной задачи оба старых Scheduled Tasks выключены,
product processes отсутствуют, локальный порт свободен, публичный HTTPS вернул
403. Временное live окно **NOT RUN**, model turns и ASR inference C5 runtime
проверок — ноль. Постоянная активация, tag/release и запуск C6 не выполнялись.
Git publication сама по себе не меняет эти факты.
