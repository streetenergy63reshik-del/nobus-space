> Состояние5 сентября2026: протокол3 и выбранный small завершили конечную квалификацию. Ниже сохранено описание подготовки4 сентября; оно не разрешает новые runs/settings и не описывает текущий расход. Действующие результаты и ограничения — [C2 HANDOFF](../../../docs/gates/gate-c2-voice-parity/HANDOFF.md), [агрегат](../../../docs/gates/gate-c2-voice-parity/CONFIRMED-QUALIFICATION.json). Для offline пересчёта сохранённых receipts: `python tests/gate_c2/qualification/aggregate_confirmed.py --repo . --evidence .runtime/c2/closure/confirmed-protocol --output .runtime/c2/closure/recomputed-confirmed.json` (новый output, ASR/provider0). Runtime factory закрепляет small и проверяет5SHA; evaluator использует те же decoding options с явным local model path. Старые hashes и FAIL не заменяются.

# Проверка настроек на development-наборе

4 сентября 2026, после первого matched dev-прогона. Контрольные hypotheses
не получены и не просмотрены. CURRENT и challenger пока не квалифицированы.
Первые расшифровки показали проблемы с именами и границами слов; большой
CURRENT prompt содержит много посторонних доменных слов. Проверяем влияние
контекста и beam search без изменения модели, эталонов или scorer.

До новых запусков закреплены три отдельных FW-кандидата:

- `fw-neutral.json`: короткий контекст с прежними English terms, прежний beam.
- `fw-wide.json`: без initial prompt, прежние English terms как hotwords,
  beam16/patience2, без previous-text conditioning.
- `fw-plain.json`: без prompt/hotwords, beam5/patience1, без conditioning.

Применяются только к прежним 16 dev audio; эталонные предложения, имена,
ошибочные hypotheses и исправленные ответы в prompt не подставляются.
Кандидат выбирается по прежним hard thresholds и независимой semantic rubric.
Ни один прогон не изменяет CURRENT задним числом. Holdout открывается только
после dev-выбора. Неуспешные варианты сохраняются в evidence; совпадение после
ручного исправления не является точностью исходного распознавания.
