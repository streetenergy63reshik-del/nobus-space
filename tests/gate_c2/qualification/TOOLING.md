> Состояние5 сентября2026: протокол3 и выбранный small завершили конечную квалификацию. Ниже сохранено описание подготовки4 сентября; оно не разрешает новые runs/settings и не описывает текущий расход. Действующие результаты и ограничения — [C2 HANDOFF](../../../docs/gates/gate-c2-voice-parity/HANDOFF.md), [агрегат](../../../docs/gates/gate-c2-voice-parity/CONFIRMED-QUALIFICATION.json). Для offline пересчёта сохранённых receipts: `python tests/gate_c2/qualification/aggregate_confirmed.py --repo . --evidence .runtime/c2/closure/confirmed-protocol --output .runtime/c2/closure/recomputed-confirmed.json` (новый output, ASR/provider0). Runtime factory закрепляет small и проверяет5SHA; evaluator использует те же decoding options с явным local model path. Старые hashes и FAIL не заменяются.

# Исполнимые средства B01

Готовы для root review/copy/freeze: `scorer.py`, `render.py`, `render_tts.ps1`, `test_tools.py`, `CORPUS-GOLD.json`, `NORMALIZATION-GOLD.json`; методический контракт — `PLAN.md`. Скрипты используют стандартную библиотеку Python и уже установленный Windows System.Speech. Точный путь установленного Python задаёт root. Новых зависимостей нет.

15 unit checks завершились успешно 4 сентября 2026: все 10 positive и 15 negative gold pairs, critical numeric spans/отрицания, знак ASCII/Unicode minus, даты, запрет lexical brand repair, явный учёт неполного timing, PCM roundtrip, реальные паузы, noise seed/SNR и защита от clipping. PowerShell script прошёл синтаксическую проверку. **TTS, ASR, compiler, model import и network не запускались.** Установленный голос и фактический TTS output root проверяет при разрешённом render.

После копирования в `tests/gate_c2/qualification/` запуск unit checks из C2 checkout:

```powershell
& '<canonical>\.venv\Scripts\python.exe' -I -S -B 'tests/gate_c2/qualification/test_tools.py'
```

Renderer по умолчанию только проверяет frozen recipes и печатает PLAN_ONLY. Только явный аргумент `--execute-tts` запускает System.Speech. Root передаёт новый отсутствующий output directory; существующий не перезаписывается. Он генерирует ровно 16 **holdout**, не читает и не меняет прежние dev WAV.

```powershell
& '<canonical>\.venv\Scripts\python.exe' -I -S -B 'tests/gate_c2/qualification/render.py' --output '.runtime/c2/closure/qualification-audio-v1'
& '<canonical>\.venv\Scripts\python.exe' -I -S -B 'tests/gate_c2/qualification/render.py' --output '.runtime/c2/closure/qualification-audio-v1' --execute-tts
```

Полный render сохраняет raw TTS segments, финальные PCM16 mono 16000Hz WAV и `render-receipt.json`: recipe, voice/assembly metadata, text/audio/tool hashes, duration/RMS/peak/clipping, реальные offsets/длины пауз, seed и измеренный SNR. Volume25 — установленное управление TTS; не обещание амплитуды ровно25%. Noise SNR измеряется на исходных ненулевых PCM samples. Общий gain применяется лишь при риске clipping и записывается. При ошибке новый partial output сохраняется как незавершённый evidence; не подменять его успешным receipt. Ограничение каждого WAV300s. Внутренний TTS subprocess имеет timeout600s; общий resource supervisor принадлежит root.

До первой новой ASR root замораживает полный manifest с хэшами новых audio и прежних dev audio, gold, scorer/renderer/runner, runtime/model assets, decoding config, exact CPU affinity и resource limits. Полезно сначала проверить dev; удерживать holdout hypotheses закрытыми до окончательного выбора config. Никакие новые hypotheses мной не читались.

Scorer принимает отдельный JSON с `measurements`, где каждая строка содержит `id`, `iteration` (0..2), исходный `hypothesis`, `seconds`, `duration`. Ошибка распознавания остаётся строкой с пустым hypothesis и явным `error`; строки не пропускать. JSON содержит только разрешённые synthetic observations. Root сопоставляет скрытый engine ID отдельно.

```powershell
& '<canonical>\.venv\Scripts\python.exe' -I -S -B 'tests/gate_c2/qualification/scorer.py' --dev-dataset 'tests/gate_c2/dataset.json' --hypotheses '.runtime/c2/closure/engine-a-raw.json' --output '.runtime/c2/closure/engine-a-score-v1' --engine-id 'A' --split all --passes 3
```

`scores.json` содержит обе lexical версии, числители/знаменатели, all/dev/holdout, completeness, invalid timing, critical mismatch по всем повторам и latency/RTF. Сводные WER/CER используют первый проход; повторы не увеличивают число языковых cases. `complete=false`, measurement error или invalid/missing timing не допускают полного PASS. Заявления PASS/KEEP/REPLACE scorer не выдаёт. Critical token threshold0 сохраняется: typed-value atoms не стирают критические числа, legacy surface mismatch остаётся рядом. Critical marker count не является semantic score.

`semantic-review.json` — отдельная worksheet с reference, raw hypothesis, заранее заданным gold и семью null-полями. Reviewer выставляет применимые dimension outcomes и обоснование независимо от compiler. Null значит unresolved. Повторы с одинаковым hypothesis объединены в один review item, список iterations сохранён. Факты gold — ожидания смысла, не authority и не готовый SemanticProposal. Summary semantic fields остаются null до отдельной независимой оценки и adjudication.

## Бюджет GigaAM

Число слов по простому whitespace split: dev235, новый holdout354, всего589; это2,506 объёма прежних16dev. Исторический 16dev×3 + concurrency2 занимал около81–85s, но его ресурсы/граница cold не равны новому matched protocol. Поэтому это лишь ориентир, не обещание нового времени и не новый benchmark.

Для 32cases×3 warm observations плюс две одновременно принятые задачи, обработанные одним serial slot, рабочая оценка warm/setup — до360s. Три process-cold пробы имеют индивидуальный максимум120s, ещё до360s. **Консервативный planning maximum —900s совокупного GigaAM execution**, включая запас180s. Root должен действительно ограничить весь запуск внешним deadline900s и индивидуальные probes; при исчерпании — terminate/INCOMPLETE, а не продление или выборочное исключение samples. 900s < оставшихся1630s; остаётся730s резерва исходной авторизации, не новый разрешённый бюджет. Матched4CPU может изменить скорость, поэтому достаточность времени подтверждается только фактическим ledger.

Оба engine получают одинаковые4 logical CPUs/4GiB/один native slot, одинаковые WAV bytes. Конкурентная проба — одновременный admission2, последовательное обслуживание1, с учётом wait/service/end-to-end. Этот renderer/scorer не запускает benchmark, не выставляет CPU affinity и не является lifetime supervisor.
