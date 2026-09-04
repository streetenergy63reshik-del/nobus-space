# B01: matched runner

Продолжение small: `--engine fw --small-budget` использует отдельно разрешённую
модель только из `.runtime/asr-qualification/faster-whisper-small/models`
и единственный `execution-ledger.json` рядом. До каждого запуска резервируется
его полная длительность; завершённый запуск списывает фактическое время,
незавершённый сохраняет резерв. Общий предел 1200 секунд, без смешивания с GigaAM.
Регрессии счётчика: `python -m pytest tests/gate_c2/qualification/test_runner_budget.py -q`.
Это проверка учёта, она не вызывает модель.

Первый small dev завершён: 16/16, WER 6,64%, CER 1,27%, critical errors 2,
raw RTFp95 0,792. **Hard FAIL**; дальнейшие конфигурации и holdout не запускались.
Источник — experiment-freeze и results/dev-0 в том же разрешённом каталоге,
агрегаты и exact hashes — C2 DEVELOPMENT-RESULTS/EVIDENCE. Остальной текст
ниже описывает исходный matched runner и прежние команды base/GigaAM.

`runner.py` готов для root review/copy/freeze. Проверены 7 pure helper tests из `test_runner.py`: ctypes layouts, отсутствие model imports при загрузке, atomic JSON, неиспользованный резерв после аварии остаётся списанным, отказ при отрицательном usage/изменении бюджета, извлечение exact CURRENT config из AST и передача absolute paths. ASR, TTS, Windows Job/subprocess runtime мной не выполнялись. Проверка реальных Job assignment, nested FW child и inference остаётся у первого ограниченного root run.

Root копирует runner рядом с `scorer.py` и gold. Перед запуском внешний root validator проверяет полный frozen manifest: candidate/source files, scripts, audio, модели и runtime/pins. Runner не читает этот manifest и не подменяет проверку hashes записыванием новых. Он сохраняет собственный digest и gold/dataset/audio/config bindings. Source CURRENT options извлекаются без импорта bot/compiler; при изменении beam8/patience1.2/ru/int8/base/VAD/previous_text контракт отклоняется. Base identifier заменён на явный абсолютный путь pinned local snapshot; `download_root` для resolved snapshot не нужен. Prompts/hotwords извлечены из фактического CURRENT script.

Запускать от корня C2, передавая selected engine **venv Python**, не system Python. `--models` для FW — готовый local base snapshot с model.bin; для Giga — уже установленный models directory, содержащий ASR files и silero/. Ничего не загружается и не устанавливается.

```powershell
& '<canonical>\.venv\Scripts\python.exe' -I -B 'tests/gate_c2/qualification/runner.py' --engine fw --split dev --iteration 0 --repo '<C2>' --corpus 'tests/gate_c2/qualification/CORPUS-GOLD.json' --dev-dataset 'tests/gate_c2/dataset.json' --dev-audio '<historical-dev-audio>' --holdout-audio '.runtime/c2/closure/qualification-audio-v2/audio' --models '<pinned-fw-base-snapshot>' --output '.runtime/c2/closure/fw-dev-0.json' --timeout 150

& '.runtime/asr-qualification/gigaam-onnx/venv/Scripts/python.exe' -I -B 'tests/gate_c2/qualification/runner.py' --engine giga --split dev --iteration 0 --repo '<C2>' --corpus 'tests/gate_c2/qualification/CORPUS-GOLD.json' --dev-dataset 'tests/gate_c2/dataset.json' --dev-audio '<historical-dev-audio>' --holdout-audio '.runtime/c2/closure/qualification-audio-v2/audio' --models '.runtime/asr-qualification/gigaam-onnx/models' --output '.runtime/c2/closure/giga-dev-0.json' --ledger '.runtime/c2/closure/giga-budget-ledger.json' --timeout 150
```

Для остальных проходов менять `--iteration`/`--split`/новый `--output`; тот же единственный Giga ledger обязателен. `--concurrency` добавляет после выбранных16samples одновременный admission двух первых cases этого split, один serial asyncio lock/native slot для обоих engine. Эти строки сохраняются отдельно от lexical denominator. Достаточно одной сопоставимой concurrency probe на engine; root выбирает одинаковый проход. До dev выбора holdout не запускать.

Каждый CLI run — fresh process, cold probe на историческом dev/direct, затем выбранные16warm cases одного iteration. Шесть запусков дают шесть process-cold observations: не переименовывать warm или отбирать лучшие три. Supervisor меряет before interpreter spawn → finished first dev-direct transcript по общему Windows performance clock; `first_transcript_usable` отдельно отмечает пригодность. Worker даёт import/load/first phases. FW load includes isolated child imports + existing encoder warmup; Giga load includes ASR/VAD sessions. Сравнимая общая cold граница важнее этих разных внутренних разложений. OS cache не очищается.

Именованный Windows Job создаётся supervisor с общей commit memory4GiB, per-process4GiB, affinity15 и kill-on-close. Реальный worker входит в Job до model imports, затем закрывает свой handle; единственный постоянный handle у supervisor. Так venv redirector не запускает native work вне Job. FW потом запускает production isolated child внутри того же внешнего дерева. Child/run CPU и peak committed job memory берутся через QueryInformationJobObject; peak working set не подменяется этим названием. Python socket audit и offline flags не доказывают native egress isolation. ORT telemetry отключена до sessions.

Сервисное время включает чтение/проверку immutable WAV и actual decode/ASR/IPC. Wait/service/end-to-end сохраняются отдельно. Raw synthetic hypotheses пишутся atomic после каждой строки только в runtime JSON; stdout содержит counts/timings. Ошибки оставляют строку с пустым hypothesis и безопасным type/code. Незавершённые строки после timeout/аварии добавляются явно. `complete` означает завершённую серию, **не** качество/PASS; error rows, unusable cold, timing/threshold failures остаются самостоятельными основаниями отказа.

Giga ledger стартует с уже израсходованных169.234s, исходный лимит1800s, remaining1630.766s; дополнительный conservative qualification cap900s. Перед model запуском под exclusive Windows file lock полностью резервируется timeout (default150s, диапазон10..300s). При штатном завершении резерв заменяется фактическим elapsed; после parent crash полный резерв остаётся charged. Другой одновременный runner не получает lock. Ledger/path нельзя удалять, переименовывать или менять для нового бюджета. Отдельного reset CLI нет.

Supervisor начинает kill за6s до конца текущего резерва и вводит отдельную общую cold deadline120s. Job закрывается в finally, остаточные процессы завершаются. Все Giga runs подряд используют один ledger, поэтому timeout не перезапускает cumulative allowance. Default6×150s не обещает completion: тяжёлый case или Job/runtime failure сохраняет INCOMPLETE evidence; лимит не продлевать и samples не выкидывать. При внешнем принудительном останове root должен сохранить ledger с полным неокончательным reservation и частичный JSON.

После серии root объединяет `measurements` каждого engine в один input JSON с уникальными(id,iteration) и запускает frozen scorer отдельно. `cold_first` и `concurrency_measurements` не добавляются в denominator; они имеют своё назначение. Полная семантическая независимая оценка — отдельное поручение.
