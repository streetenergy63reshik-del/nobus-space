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
