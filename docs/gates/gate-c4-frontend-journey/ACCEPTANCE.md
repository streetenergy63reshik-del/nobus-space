# Gate C4 — приёмка

**Обновление 8 сентября: C4 REWORK / NOT ACCEPTED / NOT PUBLISHED.** Настоящий владелец получил ответ и TXT, но обнаружил задержку подтверждения и отказ Mini App. [Исправления и доказательства](SMOKE-REWORK.md). Ниже сохранены результаты предыдущего локального checkpoint; они не принимают новый код.

**LOCAL VERIFIED / LIVE E2E PENDING / NOT ACCEPTED / NOT PUBLISHED.**
C5–C6 HOLD; MVP1 NOT READY. Разрешение владельца на необходимые проверки и
публикацию после полного PASS получено; повторная авторизация каждого шага не нужна.

База C3: `b9283b3419928042c80278b5088b526edebab6e7`,
tree `77062335b1dbccb3694721d357e484c856ac89c7`.
Проверенный C4 code: `a869a691293e45a1a3e65303be627d684acfa16e`,
tree `9a7cab97fb9947ebdfedeb5baffa57f9627a4c98`.
Ненормативное обновление active docs имеет отдельную provenance; исходные
кодовые verdict не переименовываются SHA документационного commit.

Полный L1 на этом коде: 2132 PASS, 25 subtests PASS, 2 Windows symlink SKIP,
1 historical deselect; Node17 PASS. Семь actual local scenarios и шесть отдельных
restart/replay проверены независимыми L2/L3. Первоначальный C4 REJECT сохранён.

Настоящий владелец ещё не прошёл Telegram/Mini App text/confirmed voice/clarification,
result/copy/file и recovery/re-auth на кандидате. Снимки 320/390/768,
light/dark и keyboard-only также отсутствуют. Штатные Browser/Windows tools
возвращают trusted RPC package startup error. Это реальный пробел приёмки,
который не закрывается локальной симуляцией или source inspection.

Вторая временная попытка доказала рабочие health/readiness и exact static UI
через существующий HTTPS route. История обеих попыток, реальные inputs/outputs,
завершение процессов и readback представлены в [LIVE-SMOKE](LIVE-SMOKE.json).
Рабочий route сам по себе не доказывает пользовательский путь.

Полный пакет: [HANDOFF](HANDOFF.md), [EVIDENCE](EVIDENCE.json),
[CODE-MANIFEST](CODE-MANIFEST.json), [MANIFEST](MANIFEST.json),
[UX и gaps](UX-MATRIX.md), [negative matrix](NEGATIVE-MATRIX.md),
[локальные journeys](LOCAL-JOURNEYS.json), [tests](TEST-RECEIPTS.json),
[reviews](REVIEW-VERDICTS.json), [screenshots](SCREENSHOTS.json),
[preservation](PRESERVATION.json).

До настоящего полного C4 PASS публикация не выполняется. Защита main и
обязательные checks/reviews не обходятся. NO TAG / RELEASE / PERMANENT PRODUCTION DEPLOY.
